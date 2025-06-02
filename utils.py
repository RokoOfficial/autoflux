import concurrent.futures
import time
import os
import numpy as np
import pandas as pd # Mantido se _find_data_arg o utiliza
from functools import wraps
# 'deque' não estava sendo usado, removido para limpeza.
from threading import Lock
import logging
from typing import Callable, List, Any, Dict, Optional, Tuple # Adicionado type hints

# Configuração de logging aprimorada
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [AutoFlux] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("AutoFlux") # Nome do logger consistente

class AutoFlux:
    """
    Versão aprimorada e segura do AutoFlux para paralelização controlada.
    Mantém arquitetura de núcleos principais e subnúcleos com limites configuráveis.
    """
    def __init__(self, max_main_cores: int = 3, max_sub_cores: int = 10):
from typing import Callable, List, Any, Dict, Optional, Tuple # Adicionado type hints

# Configuração de logging aprimorada
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [AutoFlux] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("AutoFlux") # Nome do logger consistente

class AutoFlux:
    """
    Versão aprimorada e segura do AutoFlux para paralelização controlada.
    Mantém arquitetura de núcleos principais e subnúcleos com limites configuráveis.
    """
    def __init__(self, max_main_cores: int = 3, max_sub_cores: int = 10):
        self.max_main_cores = min(max_main_cores, 3)  # Limite superior fixo
        self.max_sub_cores = min(max_sub_cores, 10) # Limite superior fixo
        self.safe_mode = self._check_environment()
        self.resource_lock = Lock()  # Lock existe, mas não é usado ativamente neste código.
                                     # Poderia ser usado para controlar acesso a recursos compartilhados se necessário.
        
        logger.info(f"AutoFlux inicializado. Limite de núcleos principais: {self.max_main_cores}, Limite de subnúcleos por principal: {self.max_sub_cores}")
        if self.safe_mode:
            logger.warning("MODO SEGURO ATIVADO devido a restrições de ambiente detectadas ou falta de 'psutil'. "
                         "O paralelismo pode ser limitado ou desativado.")

    def _check_environment(self) -> bool:
        """Verifica se estamos em ambiente com restrições de permissão ou sem psutil."""
        try:
            os.cpu_count()  # Teste básico de interação com o SO
            import psutil
            psutil.cpu_percent(interval=0.01) # Teste breve da funcionalidade do psutil
            logger.info("Biblioteca 'psutil' detectada e funcional. Modo seguro não forçado por esta verificação.")
            return False # Não está em modo seguro se psutil funcionar
        except ImportError:
            logger.warning("Biblioteca 'psutil' não encontrada. Ativando modo seguro como precaução para paralelismo de processos.")
            return True
        except Exception as e:
            logger.warning(f"Falha ao verificar o ambiente com 'psutil' ou 'os.cpu_count' (Erro: {e}). "
                         "Ativando modo seguro como precaução.")
            return True

    def _find_data_arg(self, args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Optional[List[Any]]:
        """
        Localiza o argumento iterável principal. Prioriza o kwarg 'data',
        depois o primeiro argumento posicional que seja uma lista, tupla, ndarray ou Series.
        Converte para lista para processamento consistente.
        """
        data_source: Any = None
        self.data_source_was_kwarg = False # Flag para _prepare_call_args
        self.data_source_original_arg_idx = -1 # Flag para _prepare_call_args

        if 'data' in kwargs:
            data_source = kwargs['data']
            self.data_source_was_kwarg = True
        else:
            for i, arg in enumerate(args):
                if isinstance(arg, (list, tuple, np.ndarray, pd.Series)):
                    data_source = arg
                    self.data_source_original_arg_idx = i
                    break
        
        if data_source is None:
            logger.debug("Nenhum argumento de dados iterável encontrado por _find_data_arg.")
            return None
        
        if isinstance(data_source, pd.DataFrame):
            logger.warning("DataFrame passado como argumento de dados. AutoFlux não implementa chunking otimizado para DataFrames. "
                           "A função decorada receberá o DataFrame inteiro ou chunks de linhas se convertido para lista. "
                           "Considere adaptar a função ou a forma como os dados são passados.")
            # Para este exemplo, não vamos converter DataFrame automaticamente para lista de linhas,
            # pois a função decorada pode esperar o DataFrame.
            # Se for para ser processado em chunks, a conversão deve ser explícita ou a função adaptada.
            # Para o propósito de len() e chunking, se for pequeno, pode passar.
            # Se for grande e a função não espera o DF inteiro, o usuário deve ajustar.
            return list(data_source.to_records(index=False)) # Exemplo: converte para lista de tuplas (linhas)

        if not isinstance(data_source, list):
            try:
                return list(data_source) # Converte tuplas, np.ndarray, pd.Series para lista
            except TypeError:
                logger.error(f"Não foi possível converter o argumento de dados do tipo {type(data_source)} para uma lista.")
                return None
        return data_source

    def _prepare_call_args(self, func_original_args: Tuple[Any, ...], 
                           func_original_kwargs: Dict[str, Any], 
                           data_iterable_as_list: List[Any], # O iterável original já convertido para lista
                           chunk_to_process: List[Any]) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
        """
        Prepara os *args e **kwargs para chamar 'func' passando 'chunk_to_process'
        no lugar do 'data_iterable_as_list' original.
        Usa flags definidas por _find_data_arg.
        """
        call_args_list = list(func_original_args)
        call_kwargs_dict = func_original_kwargs.copy()

        if self.data_source_was_kwarg:
            call_kwargs_dict['data'] = chunk_to_process
        elif self.data_source_original_arg_idx != -1:
            # Verifica se o objeto original ainda está na posição esperada
            # Isso pode ser frágil se args foi modificado entre _find_data_arg e aqui.
            # Assume que func_original_args são os argumentos com os quais a função decorada foi chamada.
            if self.data_source_original_arg_idx < len(call_args_list) and \
               type(call_args_list[self.data_source_original_arg_idx]) == type(data_iterable_as_list): # Checagem frágil
                call_args_list[self.data_source_original_arg_idx] = chunk_to_process
            else: # Fallback se a substituição posicional for incerta
                  # Assume que a função decorada aceita o chunk como primeiro argumento se não for kwarg 'data'
                  # E que os outros args originais são passados depois.
                  # Esta é a convenção dos exemplos de AutoFlux (ex: func(data_chunk, arg1, arg2...))
                logger.debug(f"_prepare_call_args: Usando convenção de chunk como primeiro argumento posicional.")
                return (chunk_to_process,) + func_original_args[1:], call_kwargs_dict

        else:
            # _find_data_arg não setou as flags, o que não deveria acontecer se data_iterable não é None.
            # Como um fallback muito simples, assuma que o chunk é o primeiro argumento.
            logger.warning("_prepare_call_args: Flags de fonte de dados não definidas. Assumindo chunk como primeiro argumento.")
--
                        # ou não conseguiu convertê-lo para lista. Nesse caso, roda sequencial.
                        if data_for_auto and len(data_for_auto) > 100: # Limite para usar threads
                            logger.info(f"Estratégia 'auto' para '{func_name}' selecionou THREADS (tamanho dos dados: {len(data_for_auto)}).")
                            return self._thread_strategy(func, *args, **kwargs)
                        else:
                            data_len_info = len(data_for_auto) if data_for_auto is not None else "N/A ou não iterável principal"
                            logger.info(f"Estratégia 'auto' para '{func_name}' selecionou SEQUENCIAL (tamanho dos dados: {data_len_info}).")
                            return func(*args, **kwargs)
                    
                    # Se chegou aqui, a estratégia não é válida
                    logger.error(f"Estratégia desconhecida ou inválida '{strategy}' fornecida para '{func_name}'. Executando sequencialmente.")
                    return func(*args, **kwargs)

                except Exception as e:
                    logger.error(f"Falha crítica na execução paralela de '{func_name}' com estratégia '{effective_strategy}': {e}. "
                                 f"Executando '{func_name}' sequencialmente como fallback final.", exc_info=True)
                    return func(*args, **kwargs) # Fallback final para a execução sequencial original
            return wrapper
        return decorator

    def _thread_strategy(self, func: Callable, *args, **kwargs) -> List[Any]:
        """Estratégia baseada em threads. Relança exceções para o fallback principal."""
        data_iterable = self._find_data_arg(args, kwargs) # Retorna uma lista ou None
        
        if data_iterable is None:
            logger.info(f"Nenhum dado iterável claro encontrado para '{func.__name__}' em _thread_strategy. "
                        "A função será chamada sequencialmente uma vez (pode ser um erro se esperava iterar).")
            return func(*args, **kwargs) # Ou raise? Se a função DEVERIA ter dados iteráveis.
                                         # Para AutoFlux, se não há dados para paralelizar, chamar uma vez é o comportamento esperado.
            
        data_size = len(data_iterable)
        if data_size == 0:
            logger.info(f"Dados vazios fornecidos para '{func.__name__}' em _thread_strategy.")
            return [] 

        num_cpus = os.cpu_count() or 1 # Garante pelo menos 1
        # Limita workers pelo número de CPUs (x2 para I/O bound), max_sub_cores e tamanho dos dados
        workers = min(self.max_sub_cores, data_size, num_cpus * 2) 
        chunk_size = max(1, (data_size + workers - 1) // workers) # Divisão de trabalho mais equilibrada
        
        logger.info(f"Estratégia de Threads para '{func.__name__}': {workers} workers, chunk size ~{chunk_size} (total de {data_size} itens).")
        
        results = []
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                futures_map = {} # Para mapear future para chunk, se necessário para debug
                for i in range(0, data_size, chunk_size):
                    chunk = data_iterable[i:i + chunk_size]
                    
                    # Prepara os argumentos para 'func' ser chamada com 'chunk'
                    submit_args, submit_kwargs = self._prepare_call_args(args, kwargs, data_iterable, chunk)
--
                    # A função 'func' decorada (wrapper) deve retornar uma lista de resultados para o chunk.
                    if isinstance(task_result, list):
                        results.extend(task_result)
                    else:
                        # Se a função decorada retorna um valor único por chunk (menos comum para os exemplos)
                        results.append(task_result)
        except Exception as e_inner_thread:
            logger.error(f"Erro durante a execução paralela em _thread_strategy para '{func.__name__}': {str(e_inner_thread)}. "
                         "Relançando para ser tratado pelo fallback principal do decorador.", exc_info=False) # exc_info=True no log principal
            raise # Relança a exceção para o try-except mais externo no decorador 'parallel'
            
        return results

    def _process_strategy(self, func: Callable, *args, **kwargs) -> List[Any]:
        """Estratégia híbrida: processos no nível superior, e cada processo usa _thread_strategy."""
        data_iterable = self._find_data_arg(args, kwargs)

        if data_iterable is None:
            logger.info(f"Nenhum dado iterável claro encontrado para '{func.__name__}' em _process_strategy. "
                        "Executando sequencialmente.")
            return func(*args, **kwargs)
        
        data_size = len(data_iterable)
        if data_size == 0:
            logger.info(f"Dados vazios fornecidos para '{func.__name__}' em _process_strategy.")
            return []

        num_cpus = os.cpu_count() or 1
        num_processes = min(self.max_main_cores, data_size, num_cpus)
        
        # Divisão de lotes (batches) para cada processo
        batch_size = max(1, (data_size + num_processes - 1) // num_processes)
        batches = [data_iterable[i:i + batch_size] for i in range(0, data_size, batch_size)]
        
        logger.info(f"Estratégia de Processos para '{func.__name__}': {num_processes} processos principais. "
                    f"Cada processo usará _thread_strategy internamente para seu lote.")
        results = []
        
        try:
            with concurrent.futures.ProcessPoolExecutor(max_workers=num_processes) as executor:
                futures = []
                for batch_idx, batch_data_chunk in enumerate(batches):
                    if len(batch_data_chunk) > 0:
                        # Para cada processo, preparamos os argumentos para chamar _thread_strategy.
                        # _thread_strategy espera (func, *args_da_func_original_com_batch_no_lugar_de_data, **kwargs_da_func_original)
                        # args e kwargs aqui são os argumentos originais da função decorada.
                        # Precisamos passar 'func' e os argumentos de 'func', onde o iterável original é substituído por 'batch_data_chunk'.
                        
                        # O primeiro argumento para _thread_strategy é 'func'.
                        # Os *args e **kwargs subsequentes são aqueles que 'func' espera.
                        prepared_args_for_func, prepared_kwargs_for_func = self._prepare_call_args(
