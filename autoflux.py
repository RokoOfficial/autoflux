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
            return (chunk_to_process,) + func_original_args[1:], call_kwargs_dict


        return tuple(call_args_list), call_kwargs_dict

    def parallel(self, strategy: str = 'auto') -> Callable:
        """Decorador principal para habilitar paralelismo com fallback seguro."""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                nonlocal strategy # Permite que a estratégia seja modificada internamente se 'auto'
                
                func_name = func.__name__
                effective_strategy = strategy

                if self.safe_mode and effective_strategy not in ['sequential', 'safe_sequential']: # Adicionado 'safe_sequential'
                    logger.info(f"Modo seguro ativo. Forçando estratégia 'sequential' para '{func_name}'.")
                    effective_strategy = 'sequential'

                if effective_strategy == 'sequential':
                    logger.info(f"Executando '{func_name}' sequencialmente (estratégia solicitada ou fallback de modo seguro).")
                    return func(*args, **kwargs)
                
                # O try-except principal que garante o fallback para execução sequencial completa.
                try:
                    if effective_strategy == 'threads':
                        logger.info(f"Executando '{func_name}' com estratégia de THREADS.")
                        return self._thread_strategy(func, *args, **kwargs)
                        
                    if effective_strategy == 'processes':
                        # Processos no Windows exigem cuidados adicionais (serialização, if __name__ == '__main__')
                        # Aqui, podemos optar por um fallback para threads no Windows ou permitir explicitamente.
                        if os.name == 'nt' and not os.environ.get('AUTOFLUX_FORCE_PROCESSES_ON_WINDOWS', 'false').lower() == 'true':
                             logger.warning("Estratégia de PROCESSOS no Windows pode encontrar problemas. "
                                           "Para forçar, defina AUTOFLUX_FORCE_PROCESSES_ON_WINDOWS=true. "
                                           f"Fazendo fallback para 'threads' para '{func_name}'.")
                             effective_strategy = 'threads' 
                             return self._thread_strategy(func, *args, **kwargs)

                        logger.info(f"Executando '{func_name}' com estratégia de PROCESSOS (híbrido processo->threads).")
                        return self._process_strategy(func, *args, **kwargs)
                        
                    if effective_strategy == 'auto':
                        data_for_auto = self._find_data_arg(args, kwargs)
                        # Se _find_data_arg retorna None, significa que não encontrou um iterável claro
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
                    
                    future = executor.submit(func, *submit_args, **submit_kwargs)
                    futures_map[future] = chunk # Opcional, para debug
                
                for future in concurrent.futures.as_completed(futures_map):
                    task_result = future.result() # Esta linha pode relançar uma exceção que ocorreu na thread
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
                            args, kwargs, data_iterable, batch_data_chunk
                        )
                        
                        logger.debug(f"Submetendo lote {batch_idx+1}/{len(batches)} (tamanho {len(batch_data_chunk)}) para ProcessPoolExecutor. "
                                     f"Processo chamará _thread_strategy(func, *args_do_lote, **kwargs_do_lote).")
                        futures.append(executor.submit(
                            self._thread_strategy, func, *prepared_args_for_func, **prepared_kwargs_for_func
                        ))
                
                for future in concurrent.futures.as_completed(futures):
                    task_result = future.result() # Pode relançar exceção
                    # _thread_strategy retorna uma lista de resultados para o lote que processou.
                    if isinstance(task_result, list):
                        results.extend(task_result)
                    else: # Improvável se _thread_strategy funciona como esperado
                        results.append(task_result)
        except Exception as e_process_pool:
            logger.error(f"Falha na ProcessPoolExecutor para '{func.__name__}': {str(e_process_pool)}. "
                         "Tentando fallback para _thread_strategy com dados completos.", exc_info=False)
            # Fallback: tentar _thread_strategy com todos os dados originais.
            # Se isso também falhar, sua exceção (re-lançada) será pega pelo decorador 'parallel'.
            return self._thread_strategy(func, *args, **kwargs) 
            
        return results

if __name__ == "__main__":
    flux = AutoFlux(max_main_cores=2, max_sub_cores=4) # Valores menores para teste rápido

    @flux.parallel(strategy='auto')
    def process_data_example(data_chunk: List[float], scale: float = 1.0) -> List[float]:
        # Esta função agora espera receber um chunk de data_list
        # logger.info(f"process_data_example processando chunk de {len(data_chunk)} itens com scale={scale}")
        time.sleep(0.001 * len(data_chunk)) # Simula trabalho proporcional ao chunk
        processed_chunk = []
        for x in data_chunk:
            # Simulação de cálculo um pouco mais complexo
            val = 0
            for i in range(100): # Pequena carga de CPU
                val += np.sin(x * scale * (i/100.0))
            processed_chunk.append(val)
        return processed_chunk

    @flux.parallel(strategy='threads')
    def analyze_texts_example(text_chunk: List[str], prefix: str = "RESULT") -> List[str]:
        # logger.info(f"analyze_texts_example processando chunk de {len(text_chunk)} com prefix={prefix}")
        time.sleep(0.002 * len(text_chunk)) # Simula I/O
        return [f"{prefix}-{text.upper()[:10]}" for text in text_chunk]

    @flux.parallel(strategy='processes')
    def cpu_bound_task_example(numbers_chunk: List[int], power: int = 2) -> List[int]:
        # logger.info(f"cpu_bound_task_example processando chunk de {len(numbers_chunk)} com power={power}")
        results_for_chunk = []
        for x in numbers_chunk:
            val = float(x)
            for _ in range(50000): # Operação CPU-intensiva (reduzida para testes mais rápidos)
                 val = (val ** power if val != 0 else 0.1) / (val + 1.00001) # Evita divisão por zero e overflow
                 val = val % 1000.0 # Mantém o número gerenciável
            results_for_chunk.append(int(val * 100))
        return results_for_chunk

    print("\n--- Teste 1: process_data_example (strategy='auto') ---")
    data_large = list(np.random.rand(10000) * 100) # AutoFlux > 1000 deve usar threads
    data_small = list(np.random.rand(100) * 100)   # AutoFlux <= 1000 deve usar sequential

    start_large = time.time()
    result_large = process_data_example(data_large, scale=1.5)
    time_large = time.time() - start_large
    print(f"Dados Grandes ({len(data_large)}): Tempo: {time_large:.3f}s | Itens Retornados: {len(result_large)} | "
          f"Exemplo: {result_large[:2] if result_large else 'N/A'} .. {result_large[-2:] if len(result_large) > 2 else ''}")

    start_small = time.time()
    result_small = process_data_example(data_small, scale=0.5)
    time_small = time.time() - start_small
    print(f"Dados Pequenos ({len(data_small)}): Tempo: {time_small:.3f}s | Itens Retornados: {len(result_small)} | "
          f"Exemplo: {result_small[:3] if result_small else 'N/A'}")

    print("\n--- Teste 2: analyze_texts_example (strategy='threads') ---")
    texts_data = [f"text_sample_{i:03d}" for i in range(50)]
    start_texts = time.time()
    analyzed = analyze_texts_example(texts_data, prefix="OUT")
    time_texts = time.time() - start_texts
    print(f"Análise de Textos ({len(texts_data)}): Tempo: {time_texts:.3f}s | Itens Retornados: {len(analyzed)} | "
          f"Exemplo: {analyzed[:3] if analyzed else 'N/A'}")
    
    # Testando com kwarg 'data'
    analyzed_kwarg = analyze_texts_example(prefix="KWARG_OUT", data=texts_data)
    print(f"Análise de Textos (kwarg 'data'): Itens Retornados: {len(analyzed_kwarg)} | "
          f"Exemplo: {analyzed_kwarg[:3] if analyzed_kwarg else 'N/A'}")


    print("\n--- Teste 3: cpu_bound_task_example (strategy='processes') ---")
    # Menos itens para tarefa CPU-bound, pois cada item é mais pesado.
    # O número de processos é pequeno (max_main_cores=2 no exemplo).
    numbers_data = list(range(8)) 
    start_cpu = time.time()
    cpu_results = cpu_bound_task_example(numbers_data, power=3)
    time_cpu = time.time() - start_cpu
    print(f"Tarefa CPU-Bound ({len(numbers_data)}): Tempo: {time_cpu:.3f}s | Itens Retornados: {len(cpu_results)} | "
          f"Exemplo: {cpu_results[:3] if cpu_results else 'N/A'}")

    print("\n--- Teste 4: Função que não tem um iterável principal claro para 'auto' ---")
    @flux.parallel(strategy='auto') # 'auto' deve ir para sequential
    def non_chunkable_func(config_dict: dict, multiplier: int, label: str = "default"):
        logger.info(f"non_chunkable_func chamada com config={config_dict}, multiplier={multiplier}, label={label}")
        time.sleep(0.01)
        return {k: v * multiplier for k, v in config_dict.items()}

    config = {'val_a': 10, 'val_b': 20}
    start_non_chunk = time.time()
    res_non_chunk = non_chunkable_func(config, multiplier=3, label="test1")
    time_non_chunk = time.time() - start_non_chunk
    print(f"Função Não Chunkable ('auto'): Tempo: {time_non_chunk:.3f}s | Resultado: {res_non_chunk}")

    print("\n--- Teste 5: Forçando erro dentro de uma thread para testar fallback ---")
    @flux.parallel(strategy='threads')
    def func_with_error_in_thread(data_chunk: List[int]) -> List[int]:
        results = []
        for i, x in enumerate(data_chunk):
            if len(data_chunk) > 1 and i == len(data_chunk) // 2 : # Erro no meio de um chunk
                logger.info(f"func_with_error_in_thread: Simulando erro para item {x} no chunk {data_chunk}")
                raise ValueError("Erro simulado dentro da thread de processamento do chunk")
            results.append(x * 10)
            time.sleep(0.001)
        return results
    
    error_data = list(range(10))
    start_error_test = time.time()
    try:
        result_error = func_with_error_in_thread(error_data)
        print(f"Teste de Erro (threads): Tempo: {time.time() - start_error_test:.3f}s | Resultado: {result_error}")
    except Exception as e:
        # Este except não deve ser atingido se o AutoFlux fizer o fallback corretamente para sequencial
        print(f"Teste de Erro (threads) - Exceção Externa: {e} (Tempo: {time.time() - start_error_test:.3f}s)")
        # Se o fallback do AutoFlux funcionar, a função func_with_error_in_thread será chamada sequencialmente com error_data.
        # E o erro acontecerá novamente, mas no fluxo sequencial, não dentro da thread.
        # O try-except do decorador @flux.parallel deve pegar e logar, depois executar sequencialmente.
        # Se o erro persistir na execução sequencial, ele será relançado por func_with_error_in_thread.
        # Vamos testar o que AutoFlux retorna:
        result_after_fallback = func_with_error_in_thread(error_data) # Isto vai falhar novamente.
        print(f"Teste de Erro (threads) - Resultado após fallback (que também falhará): {result_after_fallback}")


    logger.info("Todos os testes concluídos.")

