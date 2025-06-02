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

