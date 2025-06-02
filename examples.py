import logging
logger = logging.getLogger("AutoFlux")
import time
import numpy as np
from typing import List
from COGNITIVE.AUTOFLUX import AutoFlux
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
    def analyze_texts_example(data: List[str], prefix: str = "RESULT") -> List[str]:
        # logger.info(f"analyze_texts_example processando chunk de {len(data)} com prefix={prefix}")
        time.sleep(0.002 * len(data)) # Simula I/O
        return [f"{prefix}-{text.upper()[:10]}" for text in data]

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
