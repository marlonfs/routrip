# New-Algo Comparison — TSP

Comparativo de cinco algoritmos sobre o **Traveling Salesman Problem** (TSP):
saindo do nó 0, visitar todas as paradas uma única vez e voltar ao início,
minimizando o custo total.

| Algoritmo | Papel | Como é executado |
|-----------|-------|------------------|
| **LKH3** | Baseline | `LKH.exe` já presente em `../Algo comparison/` (subprocess, TSPLIB, `RUNS = 1`). Nenhuma biblioteca nova. |
| **ILS**  | Iterated Local Search | Biblioteca **PyVRP** (o `Model.solve()` executa a classe `IteratedLocalSearch`). |
| **ALNS** | Adaptive Large Neighbourhood Search | Biblioteca **N-Wouda/ALNS**, com operadores de remoção/inserção para o TSP. |
| **HGS**  | Hybrid Genetic Search | Biblioteca **PyHygese** (`hygese`). |
| **GNN**  | Graph Neural Network + Guided Local Search | Modelo de [walidgeuttala/atsp](https://github.com/walidgeuttala/atsp) treinado na pasta `../GNN Model/` (prediz o *regret* das arestas e guia NN + GLS). |

PyVRP e PyHygese resolvem VRP, não TSP. A adaptação modela o TSP como um **VRP de
um único veículo** (depósito no nó 0; ILS sem capacidade; HGS com demanda 1 por
cliente e capacidade `n`, forçando uma rota única = tour TSP).

## Metodologia

- Uma **matriz de distâncias simétrica** (Euclidiana inteira, TSPLIB `EUC_2D`) é
  gerada por `(n, seed)` e usada **exatamente igual** pelos cinco algoritmos.
- Parada das metaheurísticas = **iterações fixas** (ver dicts no topo de `NewTSPs.py`).
  Assim o **tempo** medido é o tempo real de execução e o **custo** mede a qualidade.
  Exceção: o **GNN** usa Guided Local Search com **orçamento de tempo** por tamanho
  (`GNN_TIME_LIMITS`), como no repositório original do modelo.
- O GNN foi treinado com instâncias da **mesma distribuição**, mas com seeds ≥ 10000
  — as seeds de teste (1..20) nunca aparecem no treino (ver `../GNN Model/README.md`).
- Instâncias: **5, 10, 20, 50 e 100** paradas, cada uma com **20 seeds**. Para cada
  seed, todos os algoritmos resolvem a mesma matriz antes de passar à próxima.
- O custo reportado é sempre `compute_tour_cost(tour, D)` com a mesma matriz inteira,
  eliminando divergências de arredondamento interno das bibliotecas.

## Requisitos

- **Python >= 3.11** (exigido pelo PyVRP / `IteratedLocalSearch`).
- Dependências (o LKH3 **não** usa biblioteca) — já estão no `requirements.txt`
  da **raiz** do repositório (`pyvrp`, `alns`, `hygese`, `numpy`, `pandas`,
  `openpyxl`; para o GNN: `torch`, `torch-geometric`, `networkx`, `scikit-learn`):

```bash
pip install -r ../requirements.txt
```

- O **GNN** requer os checkpoints treinados em `../GNN Model/checkpoints/tsp{n}/`.
  Se não existirem, gere e treine primeiro (ver `../GNN Model/README.md`).

## Como rodar

```bash
python NewTSPs.py
```

Ao final é gerado, **nesta pasta**, o arquivo `Comparação New-Algo TSPs.xlsx` com
duas planilhas:

- **`Custo`** — custo total por algoritmo / instância / seed.
- **`Tempo`** — tempo (s) por algoritmo / instância / seed.

Cada planilha tem 100 linhas (5 tamanhos × 20 seeds) e as colunas
`Instance, Seed, LKH3, ILS, ALNS, HGS, GNN`.

## Notas

- O LKH3 procura o binário nesta ordem: variável de ambiente `LKH_BINARY`
  (útil para testes em macOS/Linux), depois `../Algo comparison/LKH.exe` e
  por fim `../Algo comparison/LKH`. Em **Windows** basta o `LKH.exe` já versionado.
- Os valores de iterações (`ILS_ITERS`, `ALNS_ITERS`, `HGS_NB_ITER` no topo do
  script) e os limites de tempo do GNN (`GNN_TIME_LIMITS`) são pontos de partida
  ajustáveis conforme o orçamento de tempo desejado.
- Se um algoritmo falhar em uma instância, o valor vira `NaN` na planilha e a
  execução continua (não derruba a corrida).
