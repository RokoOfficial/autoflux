# 🌀 AutoFlux

**AutoFlux** é um sistema inteligente de paralelismo para Python que abstrai e automatiza a execução de funções em paralelo, com segurança e fallback automáticos. Ideal para tarefas que envolvem grandes volumes de dados, análise textual, processamento numérico, e mais.

---

## 🚀 Aplicações

AutoFlux pode ser aplicado em:

- 🧮 **Processamento Numérico**: operações matemáticas em lotes.
- 🧠 **Análise de Texto**: pré-processamento, tokenização ou extração de features.
- 📊 **Manipulação de Dados**: sobre listas, arrays, DataFrames.
- 🧪 **Testes Automatizados**: execução paralela de casos de teste.
- 🌐 **Tarefas de I/O**: scraping, leitura de arquivos, chamadas de API.

---

## 🧰 Instalação

```bash
# Requer Python >= 3.8
poetry install  # ou pip install .
```

---

## 🧠 Exemplo de Uso

```python
from autoflux import AutoFlux

flux = AutoFlux(max_main_cores=2, max_sub_cores=4)

@flux.parallel(strategy='auto')
def process(data: list[int]) -> list[int]:
    return [x * 2 for x in data]

result = process([1, 2, 3, 4])
```

---

## ⚙️ Estratégias Suportadas

- `'auto'`: decide entre threads e execução sequencial com base no volume.
- `'threads'`: paraleliza usando `ThreadPoolExecutor`.
- `'processes'`: usa `ProcessPoolExecutor` com fallback.
- `'sequential'`: execução normal, sem paralelismo.

---

## 🧪 Testando

Execute os testes de exemplo:
```bash
PYTHONPATH=. python3 examples.py
```

---

## 📁 Estrutura do Projeto

```
AUTOFLUX/
├── core.py          # Núcleo do sistema AutoFlux
├── utils.py         # Funções auxiliares
├── strategies.py    # Execução com threads/processos
├── decorators.py    # Decoradores paralelizadores
├── examples.py      # Testes e demonstrações
├── __init__.py      # Exportações do pacote
├── pyproject.toml   # Configuração do projeto
├── README.md        # Esta documentação
└── LICENSE          # Licença MIT
```

---

## 🔐 Segurança

- Fallback automático caso paralelismo falhe
- Controle de núcleos por camada (main/sub)
- Detecção de ambiente restrito (modo seguro)

---

## 📜 Licença

MIT License — Autor: **Roko**
