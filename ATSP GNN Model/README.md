# ATSP GNN Model — solver ATSP por Graph Neural Network

Versão para o **ATSP** (TSP assimétrico) do modelo em `../GNN Model/`, baseado
em [walidgeuttala/atsp](https://github.com/walidgeuttala/atsp) (adaptação do
GNNGLS de Hudson et al.). Aqui a matriz de distâncias é **assimétrica**
(`D[i][j] ≠ D[j][i]`) e todos os grafos são **direcionados**.

## Diferenças em relação ao GNN Model (TSP)

1. **Instâncias assimétricas** — distância Euclidiana inteira (coords em
   [0,1000]²) multiplicada por um fator aleatório `U(0.8, 1.2)` **por direção**
   (simula tráfego/sentido de vias). Mesma geradora do comparativo
   `../New ATSP Algo Comparison/NewATSPs.py`.
2. **Grafo direcionado** — `nx.DiGraph` completo com `n(n-1)` arcos (o dobro
   de arestas da versão simétrica). O *line graph* direcionado liga
   `(u,v) → (v,w)`: exatamente a semântica de continuação de um tour.
3. **Regret por arco** — fixar o arco `(i,j)` ≠ fixar `(j,i)`. O LKH resolve
   com `TYPE : ATSP`; a fixação usa `FIXED_EDGES_SECTION` com verificação de
   direção e, se o LKH não a respeitar, cai para o **mascaramento de matriz**
   (sucessor de `i` forçado a ser `j` via custos proibitivos, custo final
   recalculado com a matriz original).
4. **Or-opt no lugar do 2-opt** — o 2-opt reverte segmentos e o delta
   simétrico é inválido em matrizes assimétricas. O Or-opt reloca segmentos de
   2–3 nós **sem reversão**; o relocate (segmento de 1 nó) já era válido e foi
   mantido.

## Arquivos

| Arquivo | Papel | Base |
|---|---|---|
| `gnn_model.py` | Arquitetura GNN (`dir-gat`) | cópia de `../GNN Model/gnn_model.py` |
| `gnn_dataset.py` | Dataset (`ATSPDataset`, line graph direcionado) | `gnn_dataset.py` |
| `atsp_operators.py` | Operadores Or-opt / relocate (válidos p/ ATSP) | `gnn_operators.py` |
| `gnn_algorithms.py` | NN guiado + Guided Local Search | `gnn_algorithms.py` |
| `generate_data.py` | Instâncias assimétricas + labels de regret via LKH | `generate_data.py` |
| `train_gnn.py` | Treino (um checkpoint por tamanho) | `train_gnn.py` |
| `gnn_solver.py` | Inferência (`solve_gnn_atsp`) p/ o comparativo | `gnn_solver.py` |

Pastas criadas pelos scripts:

- `data/atsp{n}/` — instâncias rotuladas (`.pkl`), `train.txt`, `val.txt`, `scalers.pkl`;
- `checkpoints/atsp{n}/` — `checkpoint_best_val.pt`, `params.json`, `scalers.pkl`.

## Treino (reproduzir do zero)

```bash
cd "ATSP GNN Model"
python generate_data.py     # 1) dados + labels de regret (usa ../Algo comparison/LKH.exe)
python train_gnn.py         # 2) treina atsp5..atsp100 em CPU
```

Detalhes importantes:

- **Sem vazamento de teste**: o benchmark usa seeds 1..20; o treino usa a mesma
  distribuição com seeds a partir de **10000**.
- A rotulagem executa **um LKH por arco fora da solução ótima** — no ATSP são
  `n(n-1) − n` arcos (≈ 2× a versão simétrica) e o LKH trabalha internamente com
  dimensão `2n`; por isso `DATASET_SPEC` usa menos instâncias nos tamanhos
  grandes. Ambos os scripts têm *resume*.
- Hiperparâmetros padrão: `dir-gat`, `hidden_dim=64`, `num_layers=3`, `jk=cat`,
  Adam `lr=1e-3` com decaimento exponencial, early stopping.

## Uso pelo comparativo

`../New ATSP Algo Comparison/NewATSPs.py` adiciona esta pasta ao `sys.path` e chama:

```python
from gnn_solver import solve_gnn_atsp
tour = solve_gnn_atsp(distance_matrix, seed, time_limit=...)  # tour aberto começando no nó 0
```
