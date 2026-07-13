"""
Comparativo de algoritmos para o TSP — New-Algo Comparison
==========================================================

Compara cinco algoritmos sobre o Traveling Salesman Problem (sai do nó 0,
visita todas as paradas uma única vez e volta ao 0, minimizando o custo total):

    * LKH3  -> BASELINE. Usa o LKH.exe JÁ presente em "Algo comparison"
               (subprocess, TSPLIB). Nenhuma biblioteca nova.
    * ILS   -> Iterated Local Search, via PyVRP. O solve() do PyVRP executa
               internamente a classe IteratedLocalSearch (é o solver padrão),
               então usar Model.solve() = usar o ILS do PyVRP.
    * ALNS  -> Adaptive Large Neighbourhood Search, via biblioteca N-Wouda/ALNS,
               com operadores de remoção/inserção implementados para o TSP.
    * HGS   -> Hybrid Genetic Search, via PyHygese (hygese).
    * GNN   -> Graph Neural Network baseada em https://github.com/walidgeuttala/atsp:
               o modelo prediz o "regret" de cada aresta e guia um Nearest-Neighbor
               + Guided Local Search. Código, dados de treino e checkpoints ficam
               na pasta "GNN Model" (raiz do repositório).

PyVRP e PyHygese resolvem VRP, não TSP. A adaptação usada aqui modela o TSP como
um VRP de UM único veículo, sem restrição de capacidade útil (ver comentários
nos respectivos solvers).

Metodologia
-----------
* Uma única matriz de distâncias simétrica (Euclidiana inteira, estilo TSPLIB
  EUC_2D) é gerada por (n, seed) e usada EXATAMENTE IGUAL pelos quatro algoritmos.
* Critério de parada das metaheurísticas = ITERAÇÕES FIXAS (ver dicts abaixo).
  O tempo medido é o tempo real de execução; o custo mede a qualidade atingida.
  O LKH3 baseline roda sempre com RUNS = 1 (execução única natural).
* Custo reportado = compute_tour_cost(tour, D) com a MESMA matriz inteira para
  todos, eliminando divergências de arredondamento interno das bibliotecas.
* Instâncias: 5, 10, 20, 50 e 100 paradas, cada uma com 20 seeds. Para cada
  seed, todos os algoritmos resolvem a mesma matriz antes de passar à próxima.

Saída
-----
Um arquivo .xlsx na própria pasta do script, com DUAS planilhas (sheets):
    * "Custo" -> custo total por (Instância, Seed) para cada algoritmo.
    * "Tempo" -> tempo (s)   por (Instância, Seed) para cada algoritmo.

Requisitos: Python >= 3.11. Instale as dependências com:
    pip install -r requirements.txt
(O LKH3 não usa biblioteca; reutiliza o LKH.exe de "Algo comparison".)
"""

import os
import time
import random
import tempfile
import subprocess

import numpy as np
import pandas as pd

# =========================================================================
# Configuração do benchmark
# =========================================================================
# Lista de instâncias: (NUM_NODES, NUM_SEEDS)
INSTANCES = [
    (5,   20),
    (10,  20),
    (20,  20),
    (50,  20),
    (100, 20),
]

# Critério de parada = iterações fixas (ajustável). Escalam com o tamanho n.
ILS_ITERS = {5: 2000, 10: 2000, 20: 5000, 50: 10000, 100: 20000}   # iterações do ILS (PyVRP)
ALNS_ITERS = {5: 2000, 10: 2000, 20: 5000, 50: 10000, 100: 20000}  # iterações do ALNS
HGS_NB_ITER = {5: 2000, 10: 2000, 20: 5000, 50: 10000, 100: 20000}  # iters SEM melhora do HGS

# O GNN usa Guided Local Search com orçamento de TEMPO (como no repositório
# original) — limite (s) por instância, escalando com o tamanho n.
GNN_TIME_LIMITS = {5: 0.5, 10: 1.0, 20: 2.0, 50: 5.0, 100: 10.0}

# Nome do arquivo de saída (salvo na pasta deste script).
OUTPUT_FILENAME = "Comparação New-Algo TSPs.xlsx"


# =========================================================================
# Utilidades compartilhadas (mesma geração de matriz do comparativo original)
# =========================================================================
def generate_distance_matrix(num_nodes, seed):
    """Gera uma matriz de distâncias Euclidiana simétrica a partir de uma seed."""
    np.random.seed(seed)
    random.seed(seed)

    # Coordenadas 2D aleatórias em [0, 1000] x [0, 1000]
    coords = np.random.randint(0, 1001, size=(num_nodes, 2))

    # Distâncias Euclidianas arredondadas ao inteiro mais próximo (TSPLIB EUC_2D)
    distance_matrix = np.zeros((num_nodes, num_nodes), dtype=int)
    for i in range(num_nodes):
        for j in range(num_nodes):
            if i != j:
                dist = np.sqrt((coords[i][0] - coords[j][0]) ** 2 +
                               (coords[i][1] - coords[j][1]) ** 2)
                distance_matrix[i][j] = int(round(dist))
            else:
                distance_matrix[i][j] = 0
    return distance_matrix


def compute_tour_cost(tour, distance_matrix):
    """Custo total de um tour FECHADO (volta ao início). Fonte única de custo."""
    if tour is None or len(tour) < 2:
        return float('inf')
    n = len(tour)
    cost = 0
    for i in range(n):
        cost += int(distance_matrix[tour[i]][tour[(i + 1) % n]])
    return int(cost)


def solve_nearest_neighbor_tour(distance_matrix):
    """Tour heurístico do Vizinho Mais Próximo (solução inicial do ALNS)."""
    n = len(distance_matrix)
    curr = 0
    tour = [0]
    unvisited = set(range(1, n))
    while unvisited:
        next_node = min(unvisited, key=lambda x: distance_matrix[curr][x])
        tour.append(next_node)
        unvisited.remove(next_node)
        curr = next_node
    return tour


def validate_tour(tour, n):
    """Garante que o tour é uma permutação de 0..n-1 começando em 0."""
    if tour is None or len(tour) != n:
        raise ValueError(f"Tour com tamanho inesperado: {tour}")
    if tour[0] != 0:
        raise ValueError(f"Tour não começa no nó 0: {tour}")
    if sorted(tour) != list(range(n)):
        raise ValueError(f"Tour não é uma permutação de 0..{n-1}: {tour}")
    return True


# =========================================================================
# 1. LKH3 (BASELINE) — subprocess do LKH.exe já presente no repositório
# =========================================================================
def _find_lkh_binary():
    """Localiza o binário do LKH. Prioridade:
       1) variável de ambiente LKH_BINARY (útil p/ verificação local no macOS/Linux);
       2) 'Algo comparison/LKH.exe' (Windows, alvo do usuário);
       3) 'Algo comparison/LKH'     (binário compilado em Unix).
    """
    env = os.environ.get("LKH_BINARY")
    if env and os.path.exists(env):
        return env

    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    algo_dir = os.path.join(repo_root, "Algo comparison")
    for name in ("LKH.exe", "LKH"):
        candidate = os.path.join(algo_dir, name)
        if os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(
        "Binário do LKH não encontrado. Esperado 'Algo comparison/LKH.exe' "
        "(ou 'LKH'), ou defina a variável de ambiente LKH_BINARY."
    )


def solve_lkh3(distance_matrix, seed):
    """Resolve o TSP com o LKH3 (RUNS = 1) via arquivos TSPLIB e subprocess.

    Retorna o tour (0-indexado, começando no nó 0).
    """
    n = len(distance_matrix)
    lkh_path = _find_lkh_binary()

    # Arquivos temporários em um diretório isolado (limpo automaticamente).
    with tempfile.TemporaryDirectory(prefix="lkh_") as tmp:
        tsp_file = os.path.join(tmp, f"n{n}_seed{seed}.tsp")
        par_file = os.path.join(tmp, f"n{n}_seed{seed}.par")
        tour_file = os.path.join(tmp, f"n{n}_seed{seed}.tour")

        # A. Problema (matriz explícita completa)
        with open(tsp_file, "w") as f:
            f.write(f"NAME : n{n}_seed{seed}\n")
            f.write("TYPE : TSP\n")
            f.write(f"DIMENSION : {n}\n")
            f.write("EDGE_WEIGHT_TYPE : EXPLICIT\n")
            f.write("EDGE_WEIGHT_FORMAT : FULL_MATRIX\n")
            f.write("EDGE_WEIGHT_SECTION\n")
            for row in distance_matrix:
                f.write(" ".join(map(str, (int(v) for v in row))) + "\n")
            f.write("EOF\n")

        # B. Parâmetros (SEED para reprodutibilidade; RUNS = 1)
        with open(par_file, "w") as f:
            f.write(f"PROBLEM_FILE = {tsp_file}\n")
            f.write(f"OUTPUT_TOUR_FILE = {tour_file}\n")
            f.write(f"SEED = {seed}\n")
            f.write("RUNS = 1\n")

        # C. Executa o LKH
        subprocess.run(
            [lkh_path, par_file],
            capture_output=True, text=True, check=True,
        )

        # D. Lê o tour de saída (1-indexado -> 0-indexado)
        tour = []
        with open(tour_file, "r") as f:
            in_section = False
            for line in f:
                line = line.strip()
                if line.startswith("TOUR_SECTION"):
                    in_section = True
                    continue
                if in_section:
                    if line == "-1" or line == "EOF":
                        break
                    tour.append(int(line) - 1)

    if not tour:
        raise RuntimeError("Falha ao ler o tour do LKH3.")

    # Alinha o tour para começar no nó 0
    start = tour.index(0)
    return tour[start:] + tour[:start]


# =========================================================================
# 2. ILS — PyVRP (Model + solve). solve() executa o IteratedLocalSearch.
# =========================================================================
def solve_ils_pyvrp(distance_matrix, seed, max_iters):
    """Resolve o TSP com o Iterated Local Search do PyVRP.

    Adaptação TSP -> VRP: 1 veículo, sem capacidade útil (capacity=[]), depósito
    no nó 0 e um cliente por nó restante. Todas as arestas são dadas explicitamente
    pela matriz, então as coordenadas (x, y) são apenas placeholders.
    """
    from pyvrp import Model
    from pyvrp.stop import MaxIterations

    n = len(distance_matrix)
    model = Model()
    depot = model.add_depot(x=0, y=0)                       # coords irrelevantes
    clients = [model.add_client(x=0, y=0) for _ in range(n - 1)]
    locs = [depot] + clients                                # índice i <-> nó i
    model.add_vehicle_type(num_available=1, capacity=[])    # 1 veículo, sem capacidade

    for i in range(n):
        for j in range(n):
            if i != j:
                model.add_edge(locs[i], locs[j], distance=int(distance_matrix[i][j]))

    result = model.solve(stop=MaxIterations(max_iters), seed=seed, display=False)

    routes = result.best.routes()
    if not routes:
        raise RuntimeError("PyVRP não retornou nenhuma rota.")
    visits = list(routes[0].visits())                       # índices 1..n-1
    return [0] + visits


# =========================================================================
# 3. HGS — PyHygese (hygese). TSP como CVRP de 1 veículo.
# =========================================================================
def solve_hgs(distance_matrix, seed, nb_iter):
    """Resolve o TSP com o Hybrid Genetic Search (HGS-CVRP) via PyHygese.

    Adaptação TSP -> CVRP: 1 veículo; cada cliente com demanda 1 e capacidade n
    (>= demanda total), de modo que uma única rota visita todos os nós = tour TSP.
    Demanda 1 (em vez de 0) evita o aborto do HGS por "escala de demanda".
    nb_iter = número de iterações SEM melhora (controle de esforço fixo do HGS).
    """
    import hygese as hgs

    n = len(distance_matrix)
    data = {
        "distance_matrix": distance_matrix,
        "num_vehicles": 1,
        "depot": 0,
        "demands": [0] + [1] * (n - 1),
        "vehicle_capacity": n,
        "service_times": [0] * n,
    }
    # timeLimit = 0.0 -> sem limite de tempo; a parada é governada por nb_iter.
    params = hgs.AlgorithmParameters(nbIter=nb_iter, timeLimit=0.0, seed=seed)
    solver = hgs.Solver(parameters=params, verbose=False)
    result = solver.solve_cvrp(data)

    if not result.routes:
        raise RuntimeError("HGS não retornou nenhuma rota.")
    return [0] + list(result.routes[0])                     # rota exclui o depósito


# =========================================================================
# 4. ALNS — N-Wouda/ALNS com operadores de remoção/inserção para o TSP
# =========================================================================
def solve_alns(distance_matrix, seed, max_iters):
    """Resolve o TSP com ALNS (destroy = remoção aleatória, repair = inserção gulosa).

    Estado = lista ordenada de nós com o depósito 0 na frente; o custo é o do tour
    fechado. A matriz entra nos operadores por closure.
    """
    from alns import ALNS
    from alns.select import RouletteWheel
    from alns.accept import RecordToRecordTravel
    from alns.stop import MaxIterations

    D = distance_matrix
    n = len(D)

    class TspState:
        def __init__(self, route, unassigned=None):
            self.route = route                              # [0, ...]  (aberto)
            self.unassigned = unassigned if unassigned is not None else []

        def objective(self):
            return compute_tour_cost(self.route, D)

        def copy(self):
            return TspState(self.route.copy(), self.unassigned.copy())

    def random_removal(state, rng):
        """Remove ~15% dos nós (nunca o depósito, índice 0) para 'unassigned'."""
        new = state.copy()
        n_remove = max(1, int(0.15 * len(new.route)))
        removable = list(range(1, len(new.route)))
        n_remove = min(n_remove, len(removable))
        idxs = rng.choice(removable, size=n_remove, replace=False)
        for i in sorted(idxs, reverse=True):
            new.unassigned.append(new.route.pop(i))
        return new

    def greedy_repair(state, rng):
        """Reinsere cada nó não-atribuído na posição de menor delta de inserção."""
        new = state.copy()
        rng.shuffle(new.unassigned)
        while new.unassigned:
            node = new.unassigned.pop()
            best_pos, best_delta = 1, float('inf')
            L = len(new.route)
            for pos in range(1, L + 1):
                prev = new.route[pos - 1]
                nxt = new.route[pos % L]
                delta = D[prev][node] + D[node][nxt] - D[prev][nxt]
                if delta < best_delta:
                    best_delta, best_pos = delta, pos
            new.route.insert(best_pos, node)
        return new

    rng = np.random.default_rng(seed)
    alns = ALNS(rng)
    alns.add_destroy_operator(random_removal)
    alns.add_repair_operator(greedy_repair)

    init = TspState(solve_nearest_neighbor_tour(D))
    select = RouletteWheel(scores=[5, 2, 1, 0.5], decay=0.8, num_destroy=1, num_repair=1)
    accept = RecordToRecordTravel.autofit(init.objective(), 0.02, 0.0, max_iters)
    stop = MaxIterations(max_iters)

    result = alns.iterate(init, select, accept, stop)
    return result.best_state.route


# =========================================================================
# 5. GNN — modelo de walidgeuttala/atsp, treinado na pasta "GNN Model"
# =========================================================================
def solve_gnn_model(distance_matrix, seed, time_limit):
    """Resolve o TSP com o solver GNN (regret previsto + Guided Local Search).

    O modelo prediz o regret de cada aresta; um Nearest-Neighbor guiado pelo
    regret gera o tour inicial, melhorado por Guided Local Search até o limite
    de tempo. Requer os checkpoints treinados em "GNN Model/checkpoints/"
    (ver "GNN Model/README.md" para gerar dados e treinar).
    """
    import sys

    script_dir = os.path.dirname(os.path.abspath(__file__))
    gnn_dir = os.path.join(os.path.dirname(script_dir), "GNN Model")
    if gnn_dir not in sys.path:
        sys.path.insert(0, gnn_dir)
    from gnn_solver import solve_gnn

    return solve_gnn(distance_matrix, seed, time_limit=time_limit)


# =========================================================================
# Loop principal
# =========================================================================
# (nome, função(D, seed, n) -> tour). Ordem das colunas no relatório.
SOLVERS = [
    ("LKH3", lambda D, seed, n: solve_lkh3(D, seed)),
    ("ILS",  lambda D, seed, n: solve_ils_pyvrp(D, seed, ILS_ITERS[n])),
    ("ALNS", lambda D, seed, n: solve_alns(D, seed, ALNS_ITERS[n])),
    ("HGS",  lambda D, seed, n: solve_hgs(D, seed, HGS_NB_ITER[n])),
    ("GNN",  lambda D, seed, n: solve_gnn_model(D, seed, GNN_TIME_LIMITS[n])),
]


def main():
    print("Iniciando o comparativo New-Algo para o TSP...")
    print(f"Instâncias (n, seeds): {INSTANCES}")
    print(f"Algoritmos: {[name for name, _ in SOLVERS]}\n")

    cost_rows = []
    time_rows = []

    for num_nodes, num_seeds in INSTANCES:
        label = f"TSP{num_nodes}"
        print(f"\n========== {label} (seeds = {num_seeds}) ==========")

        for seed in range(1, num_seeds + 1):
            # Matriz ÚNICA compartilhada por todos os algoritmos nesta (n, seed)
            D = generate_distance_matrix(num_nodes, seed)

            cost_row = {"Instance": label, "Seed": seed}
            time_row = {"Instance": label, "Seed": seed}
            print(f"--- {label} | Seed {seed:02d} ---")

            for name, solve_fn in SOLVERS:
                try:
                    t0 = time.perf_counter()
                    tour = solve_fn(D, seed, num_nodes)
                    elapsed = time.perf_counter() - t0
                    validate_tour(tour, num_nodes)
                    cost = compute_tour_cost(tour, D)
                    cost_row[name] = cost
                    time_row[name] = elapsed
                    print(f"  [{name:<4}] Custo: {cost:<7d} | Tempo: {elapsed:.4f}s")
                except Exception as exc:
                    cost_row[name] = np.nan
                    time_row[name] = np.nan
                    print(f"  [{name:<4}] FALHOU: {exc}")

            cost_rows.append(cost_row)
            time_rows.append(time_row)

    # -----------------------------------------------------------------
    # Exporta para .xlsx com duas planilhas: "Custo" e "Tempo"
    # -----------------------------------------------------------------
    col_order = ["Instance", "Seed"] + [name for name, _ in SOLVERS]
    df_cost = pd.DataFrame(cost_rows)[col_order]
    df_time = pd.DataFrame(time_rows)[col_order]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, OUTPUT_FILENAME)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_cost.to_excel(writer, sheet_name="Custo", index=False)
        df_time.to_excel(writer, sheet_name="Tempo", index=False)

    print(f"\nResultados salvos em: {output_path}")
    print("  - Planilha 'Custo': custo total por algoritmo/instância/seed")
    print("  - Planilha 'Tempo': tempo (s)   por algoritmo/instância/seed")


if __name__ == "__main__":
    main()
