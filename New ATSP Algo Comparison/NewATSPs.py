"""
Comparativo de algoritmos para o ATSP — New ATSP Algo Comparison
================================================================

Compara cinco algoritmos sobre o ATSP (TSP ASSIMÉTRICO: sai do nó 0, visita
todas as paradas uma única vez e volta ao 0, minimizando o custo total, com
D[i][j] != D[j][i] em geral):

    * LKH3  -> BASELINE. Usa o LKH.exe JÁ presente em "Algo comparison"
               (subprocess, TSPLIB com TYPE: ATSP). Nenhuma biblioteca nova.
    * ILS   -> Iterated Local Search, via PyVRP. O solve() do PyVRP executa
               internamente a classe IteratedLocalSearch (é o solver padrão);
               as arestas são adicionadas por direção, então a matriz
               assimétrica entra nativamente.
    * ALNS  -> Adaptive Large Neighbourhood Search, via biblioteca N-Wouda/ALNS,
               com operadores de remoção/inserção (deltas direcionais, válidos
               para matrizes assimétricas).
    * HGS   -> Hybrid Genetic Search, via PyHygese (hygese). ATENÇÃO: o
               HGS-CVRP foi projetado para instâncias SIMÉTRICAS — ver a
               limitação documentada no docstring de solve_hgs.
    * GNN   -> Graph Neural Network baseada em https://github.com/walidgeuttala/atsp:
               o modelo prediz o "regret" de cada ARCO e guia um Nearest-Neighbor
               + Guided Local Search (Or-opt + relocate, válidos para ATSP).
               Código, dados de treino e checkpoints ficam na pasta
               "ATSP GNN Model" (raiz do repositório).

PyVRP e PyHygese resolvem VRP, não TSP. A adaptação usada aqui modela o ATSP
como um VRP de UM único veículo, sem restrição de capacidade útil (ver
comentários nos respectivos solvers).

Metodologia
-----------
* Uma única matriz de distâncias ASSIMÉTRICA é gerada por (n, seed) e usada
  EXATAMENTE IGUAL pelos cinco algoritmos: distância Euclidiana inteira
  (coords em [0,1000]²) multiplicada por um fator aleatório U(0.8, 1.2) POR
  DIREÇÃO (simula tráfego/sentido de vias).
* Critério de parada das metaheurísticas = ITERAÇÕES FIXAS (ver dicts abaixo).
  O tempo medido é o tempo real de execução; o custo mede a qualidade atingida.
  O LKH3 baseline roda sempre com RUNS = 1 (execução única natural).
* Custo reportado = compute_tour_cost(tour, D) com a MESMA matriz inteira para
  todos (soma direcionada no sentido do tour), eliminando divergências de
  arredondamento interno das bibliotecas.
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
OUTPUT_FILENAME = "Comparação New-Algo ATSPs.xlsx"


# =========================================================================
# Utilidades compartilhadas (mesma geração de matriz do "ATSP GNN Model")
# =========================================================================
def generate_asymmetric_distance_matrix(num_nodes, seed):
    """Matriz assimétrica: Euclidiana inteira * fator U(0.8, 1.2) por direção."""
    np.random.seed(seed)
    random.seed(seed)

    coords = np.random.randint(0, 1001, size=(num_nodes, 2))
    factors = np.random.uniform(0.8, 1.2, size=(num_nodes, num_nodes))

    distance_matrix = np.zeros((num_nodes, num_nodes), dtype=int)
    for i in range(num_nodes):
        for j in range(num_nodes):
            if i != j:
                dist = np.sqrt((coords[i][0] - coords[j][0]) ** 2 +
                               (coords[i][1] - coords[j][1]) ** 2)
                distance_matrix[i][j] = int(round(dist * factors[i][j]))
    return distance_matrix


def compute_tour_cost(tour, distance_matrix):
    """Custo total de um tour FECHADO (volta ao início). Fonte única de custo.

    A soma é DIRECIONADA (D[a][b] no sentido do tour), então já é correta
    para matrizes assimétricas.
    """
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
    """Resolve o ATSP com o LKH3 (RUNS = 1) via arquivos TSPLIB e subprocess.

    TYPE : ATSP faz o LKH aplicar internamente a transformação para TSP
    simétrico (dimensão 2n) e devolver um tour DIRECIONADO de n nós.
    Retorna o tour (0-indexado, começando no nó 0).
    """
    n = len(distance_matrix)
    lkh_path = _find_lkh_binary()

    # Arquivos temporários em um diretório isolado (limpo automaticamente).
    with tempfile.TemporaryDirectory(prefix="lkh_") as tmp:
        tsp_file = os.path.join(tmp, f"n{n}_seed{seed}.atsp")
        par_file = os.path.join(tmp, f"n{n}_seed{seed}.par")
        tour_file = os.path.join(tmp, f"n{n}_seed{seed}.tour")

        # A. Problema (matriz explícita completa, assimétrica)
        with open(tsp_file, "w") as f:
            f.write(f"NAME : n{n}_seed{seed}\n")
            f.write("TYPE : ATSP\n")
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

    # Alinha o tour para começar no nó 0 (rotação preserva a direção)
    start = tour.index(0)
    return tour[start:] + tour[:start]


# =========================================================================
# 2. ILS — PyVRP (Model + solve). solve() executa o IteratedLocalSearch.
# =========================================================================
def solve_ils_pyvrp(distance_matrix, seed, max_iters):
    """Resolve o ATSP com o Iterated Local Search do PyVRP.

    Adaptação TSP -> VRP: 1 veículo, sem capacidade útil (capacity=[]), depósito
    no nó 0 e um cliente por nó restante. Todas as arestas são dadas explicitamente
    pela matriz — add_edge cria ARCOS direcionados, então a assimetria
    (D[i][j] != D[j][i]) entra nativamente. As coordenadas (x, y) são placeholders.
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
# 3. HGS — PyHygese (hygese). ATSP como CVRP de 1 veículo.
# =========================================================================
def solve_hgs(distance_matrix, seed, nb_iter):
    """Resolve o ATSP com o Hybrid Genetic Search (HGS-CVRP) via PyHygese.

    Adaptação TSP -> CVRP: 1 veículo; cada cliente com demanda 1 e capacidade n
    (>= demanda total), de modo que uma única rota visita todos os nós = tour.
    Demanda 1 (em vez de 0) evita o aborto do HGS por "escala de demanda".
    nb_iter = número de iterações SEM melhora (controle de esforço fixo do HGS).

    LIMITAÇÃO (documentada de propósito): o HGS-CVRP foi projetado para
    instâncias SIMÉTRICAS — sua busca local inclui movimentos com REVERSÃO de
    segmento (2-opt) cujo delta assume D[i][j] == D[j][i]. Com uma matriz
    assimétrica o solver ainda roda e devolve um tour VÁLIDO, mas avalia
    internamente alguns movimentos com custo errado, então a qualidade tende a
    ser inferior à dos métodos nativamente assimétricos. O custo reportado no
    comparativo é SEMPRE recalculado externamente com a matriz assimétrica
    (compute_tour_cost), portanto o número na planilha é correto — apenas o
    tour encontrado pode ser pior. Mantido no comparativo por consistência com
    a versão TSP.
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
# 4. ALNS — N-Wouda/ALNS com operadores de remoção/inserção para o ATSP
# =========================================================================
def solve_alns(distance_matrix, seed, max_iters):
    """Resolve o ATSP com ALNS (destroy = remoção aleatória, repair = inserção gulosa).

    Estado = lista ordenada de nós com o depósito 0 na frente; o custo é o do tour
    fechado. A matriz entra nos operadores por closure. O delta de inserção
    (D[prev][node] + D[node][nxt] - D[prev][nxt]) usa apenas acessos no sentido
    do tour, então já é correto para matrizes assimétricas.
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
# 5. GNN — modelo de walidgeuttala/atsp, treinado na pasta "ATSP GNN Model"
# =========================================================================
def solve_gnn_model(distance_matrix, seed, time_limit):
    """Resolve o ATSP com o solver GNN (regret previsto + Guided Local Search).

    O modelo prediz o regret de cada ARCO; um Nearest-Neighbor guiado pelo
    regret gera o tour inicial, melhorado por Guided Local Search (Or-opt +
    relocate) até o limite de tempo. Requer os checkpoints treinados em
    "ATSP GNN Model/checkpoints/" (ver "ATSP GNN Model/README.md" para gerar
    dados e treinar).
    """
    import sys

    script_dir = os.path.dirname(os.path.abspath(__file__))
    gnn_dir = os.path.join(os.path.dirname(script_dir), "ATSP GNN Model")
    if gnn_dir not in sys.path:
        sys.path.insert(0, gnn_dir)
    from gnn_solver import solve_gnn_atsp

    return solve_gnn_atsp(distance_matrix, seed, time_limit=time_limit)


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
    print("Iniciando o comparativo New-Algo para o ATSP...")
    print(f"Instâncias (n, seeds): {INSTANCES}")
    print(f"Algoritmos: {[name for name, _ in SOLVERS]}\n")

    cost_rows = []
    time_rows = []

    for num_nodes, num_seeds in INSTANCES:
        label = f"ATSP{num_nodes}"
        print(f"\n========== {label} (seeds = {num_seeds}) ==========")

        for seed in range(1, num_seeds + 1):
            # Matriz ÚNICA compartilhada por todos os algoritmos nesta (n, seed)
            D = generate_asymmetric_distance_matrix(num_nodes, seed)

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
