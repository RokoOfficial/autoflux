# AutoFlux

AutoFlux é um sistema de paralelismo inteligente e seguro para Python, criado para facilitar a execução eficiente de funções que trabalham com coleções de dados. Com suporte a múltiplas estratégias (`sequential`, `threads`, `processes`, `auto`), o AutoFlux realiza fallback automático para execução sequencial em ambientes restritos ou em caso de erro.

---

## 🚀 Aplicações Possíveis

AutoFlux pode ser utilizado em diversos cenários, como:

- 🧮 **Processamento Numérico em Lote**: cálculos matemáticos ou científicos sobre arrays de dados.
- 🧠 **Análise de Texto em Massa**: pré-processamento, limpeza ou anotação de grandes volumes de texto.
- 🔍 **Avaliação de Modelos ou Inferência**: execução paralela de pipelines de machine learning.
- 🧪 **Testes Automatizados em Paralelo**: execução distribuída de baterias de testes.
- 📊 **Manipulação de DataFrames**: quando convertidos para listas ou iteráveis.
- 🌐 **Tarefas I/O-bound**: chamadas de rede, scraping, leitura/gravação de arquivos.

---

## 📦 Instalação

```bash
# Requer Python >= 3.8
cd COGNITIVE/AUTOFLUX
poetry install  # ou pip install .
```

---

## 🧠 Uso Básico

```python
from autoflux import AutoFlux

flux = AutoFlux(max_main_cores=2, max_sub_cores=4)

@flux.parallel(strategy='auto')
def process(data: list[int]) -> list[int]:
    return [x * 2 for x in data]

result = process([1, 2, 3, 4, 5])
```

---

## 🎯 Estratégias Suportadas

- `'auto'`: decide entre sequencial e threads baseado no tamanho dos dados.
- `'threads'`: usa `ThreadPoolExecutor` com controle de chunking.
- `'processes'`: usa `ProcessPoolExecutor` com fallback interno para threads.
- `'sequential'`: execução simples, sem paralelismo.

---

## 🧪 Testes

Execute o script de exemplo com:
```bash
PYTHONPATH=. python3 COGNITIVE/AUTOFLUX/examples.py
```

---

## 🧰 Estrutura do Projeto

```
AUTOFLUX/
├── core.py          # Classe AutoFlux
├── utils.py         # Funções auxiliares
├── strategies.py    # Lógicas de execução (threads, processos)
├── decorators.py    # Decorador parallel
├── examples.py      # Testes e demonstrações
├── __init__.py      # Exporta AutoFlux
├── pyproject.toml   # Configuração Poetry
└── README.md        # Esta documentação
```

---

## 🧩 Requisitos

- Python 3.8+
- numpy
- pandas *(opcional, usado se DataFrames forem processados)*
- psutil *(opcional, para melhor detecção de ambiente)*

---

## 🔒 Segurança e Robustez

- O sistema detecta automaticamente restrições de ambiente.
- Em caso de erro, faz fallback para modo seguro sequencial.
- Exceções internas em threads são capturadas e redirecionadas.

---

## 📜 Licença

MIT License — RokoOfficial

