# New ATSP Algo Comparison — ATSP

Comparativo de cinco algoritmos sobre o **ATSP** (TSP assimétrico): saindo do
nó 0, visitar todas as paradas uma única vez e voltar ao início, minimizando o
custo total — com `D[i][j] ≠ D[j][i]` em geral, então a **direção** do tour
importa. Mesma estrutura do comparativo TSP em `../New-Algo Comparison/`.

| Algoritmo | Papel | Como é executado |
|-----------|-------|------------------|
| **LKH3** | Baseline | `LKH.exe` já presente em `../Algo comparison/` (subprocess, TSPLIB `TYPE: ATSP`, `RUNS = 1`). |
| **ILS**  | Iterated Local Search | Biblioteca **PyVRP**; `add_edge` cria arcos direcionados, então a matriz assimétrica entra nativamente. |
| **ALNS** | Adaptive Large Neighbourhood Search | Biblioteca **N-Wouda/ALNS**; os deltas de remoção/inserção são direcionais (válidos para ATSP). |
| **HGS**  | Hybrid Genetic Search | Biblioteca **PyHygese** (`hygese`). **Ver limitação abaixo.** |
| **GNN**  | Graph Neural Network + Guided Local Search | Modelo treinado na pasta `../ATSP GNN Model/` (prediz o *regret* por **arco** e guia NN + GLS com Or-opt/relocate). |

## Instâncias assimétricas

A matriz é gerada por `(n, seed)`: distância Euclidiana inteira (coords em
[0,1000]²) multiplicada por um fator aleatório `U(0.8, 1.2)` **por direção**
(simula tráfego/sentido de vias). É a **mesma geradora** usada no treino do
GNN (`../ATSP GNN Model/generate_data.py`), com seeds de teste 1..20 e seeds
de treino ≥ 10000 (sem vazamento).

## Limitação do HGS

O HGS-CVRP foi projetado para instâncias **simétricas**: sua busca local
inclui movimentos com reversão de segmento (2-opt) cujo delta assume
`D[i][j] == D[j][i]`. Com matriz assimétrica o solver roda e devolve um tour
**válido**, mas avalia internamente alguns movimentos com custo errado — a
qualidade tende a ser inferior à dos métodos nativamente assimétricos. O custo
na planilha é sempre recalculado externamente com a matriz assimétrica
(`compute_tour_cost`), então o número reportado é correto. O HGS foi mantido
por consistência com o comparativo TSP.

## Metodologia

- Uma **matriz assimétrica única** por `(n, seed)` é usada **exatamente igual**
  pelos cinco algoritmos.
- Parada das metaheurísticas = **iterações fixas** (dicts no topo de `NewATSPs.py`).
  Exceção: o **GNN** usa Guided Local Search com **orçamento de tempo** por
  tamanho (`GNN_TIME_LIMITS`).
- Instâncias: **5, 10, 20, 50 e 100** paradas, cada uma com **20 seeds**.
- O custo reportado é sempre `compute_tour_cost(tour, D)` (soma direcionada no
  sentido do tour) com a mesma matriz inteira para todos.

## Requisitos

- **Python >= 3.11** (exigido pelo PyVRP / `IteratedLocalSearch`).
- Dependências — já estão no `requirements.txt` da **raiz** do repositório:

```bash
pip install -r ../requirements.txt
```

- O **GNN** requer os checkpoints treinados em `../ATSP GNN Model/checkpoints/atsp{n}/`.
  Se não existirem, gere e treine primeiro (ver `../ATSP GNN Model/README.md`).

## Como rodar

```bash
python NewATSPs.py
```

Ao final é gerado, **nesta pasta**, o arquivo `Comparação New-Algo ATSPs.xlsx`
com duas planilhas:

- **`Custo`** — custo total por algoritmo / instância / seed.
- **`Tempo`** — tempo (s) por algoritmo / instância / seed.

Cada planilha tem 100 linhas (5 tamanhos × 20 seeds) e as colunas
`Instance, Seed, LKH3, ILS, ALNS, HGS, GNN`.

## Notas

- O LKH3 procura o binário nesta ordem: variável de ambiente `LKH_BINARY`,
  depois `../Algo comparison/LKH.exe` e por fim `../Algo comparison/LKH`.
- Se um algoritmo falhar em uma instância, o valor vira `NaN` na planilha e a
  execução continua (não derruba a corrida).
