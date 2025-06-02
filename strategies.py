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
--
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
