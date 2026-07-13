# GNN Model — solver TSP por Graph Neural Network

Modelo de resolução do TSP por **GNN**, baseado em
[walidgeuttala/atsp](https://github.com/walidgeuttala/atsp) (por sua vez uma
adaptação do GNNGLS de Hudson et al., *Graph Neural Network Guided Local
Search for the Traveling Salesperson Problem*).

## Como funciona

1. **Regret por aresta** — para cada aresta `e` do grafo, o "regret" mede o
   quanto o custo do tour ótimo piora se `e` for forçada na solução:
   `regret(e) = (custo_com_e_fixada − custo_ótimo) / custo_ótimo`.
2. **Line graph** — a instância vira um *line graph* (cada aresta vira um nó,
   feature = peso escalado) e a GNN (`dir-gat`, convoluções direcionais GAT)
   é treinada por regressão (MSE) para prever o regret de cada aresta.
3. **Inferência** (usada pelo comparativo em `New-Algo Comparison/NewTSPs.py`):
   o regret previsto guia um **Nearest-Neighbor** (tour inicial) e um
   **Guided Local Search** (2-opt + relocate, guia = `regret_pred`) com
   orçamento de tempo por tamanho de instância.

## Arquivos

| Arquivo | Papel | Origem no repositório base |
|---|---|---|
| `gnn_model.py` | Arquitetura GNN | `src/model.py` (sem `torch_sparse`) |
| `gnn_dataset.py` | Dataset (line graph + scalers) | `src/dataset/__init__.py` |
| `gnn_operators.py` | Operadores 2-opt / relocate | `src/utils/operators.py` |
| `gnn_algorithms.py` | NN guiado + Guided Local Search | `src/algorithms.py` |
| `generate_data.py` | Gera instâncias + labels de regret via LKH | `src/generate_instances.py` + `preprocess_dataset.py` |
| `train_gnn.py` | Treino (um checkpoint por tamanho) | `src/train.py` |
| `gnn_solver.py` | Inferência p/ o comparativo | `src/test.py` |

Pastas criadas pelos scripts:

- `data/tsp{n}/` — instâncias rotuladas (`.pkl`), `train.txt`, `val.txt`, `scalers.pkl`;
- `checkpoints/tsp{n}/` — `checkpoint_best_val.pt`, `params.json`, `scalers.pkl`
  (é só disso que a inferência precisa).

## Treino (reproduzir do zero)

```bash
cd "GNN Model"
python generate_data.py     # 1) dados + labels de regret (usa ../Algo comparison/LKH.exe)
python train_gnn.py         # 2) treina tsp5..tsp100 em CPU
```

Detalhes importantes:

- **Sem vazamento de teste**: o benchmark usa seeds 1..20; o treino usa a mesma
  distribuição de instâncias (Euclidiana inteira, coords em [0,1000]²) com
  seeds a partir de **10000**.
- A rotulagem executa **um LKH por aresta fora da solução ótima** (paralelizado
  por threads) — é a etapa cara: ~2 h no total com 8 threads.
- Nº de instâncias por tamanho em `DATASET_SPEC` (`generate_data.py`); os dois
  scripts têm *resume* (reexecutar não refaz o que já existe).
- Hiperparâmetros padrão do treino: `dir-gat`, `hidden_dim=64`, `num_layers=3`,
  `jk=cat`, Adam `lr=1e-3` com decaimento exponencial 0.99, early stopping.
- Adaptações em relação ao repositório base estão documentadas nos docstrings
  de cada arquivo (ex.: remoção de `torch_sparse`, regret truncado em ≥ 0,
  device CPU).

## Uso pelo comparativo

`NewTSPs.py` adiciona a pasta ao `sys.path` e chama:

```python
from gnn_solver import solve_gnn
tour = solve_gnn(distance_matrix, seed, time_limit=...)  # tour aberto começando no nó 0
```

Os limites de tempo do GLS por tamanho ficam em `GNN_TIME_LIMITS`
(`NewTSPs.py`) e `GLS_TIME_LIMITS` (`gnn_solver.py`).
