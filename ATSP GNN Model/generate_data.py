"""
Geração do dataset de treino do GNN para o ATSP — adaptado de
"GNN Model/generate_data.py" (que por sua vez adapta
https://github.com/walidgeuttala/atsp).

Diferenças em relação à versão TSP (simétrica):
    * Matriz de distâncias ASSIMÉTRICA: Euclidiana inteira (coords em
      [0,1000]²) multiplicada por um fator aleatório U(0.8, 1.2) POR DIREÇÃO,
      então D[i][j] != D[j][i] em geral. Mesma geradora do benchmark
      (NewATSPs.py) — apenas as seeds diferem (treino >= 10000, teste 1..20).
    * O grafo da instância é DIRECIONADO (nx.DiGraph) com n(n-1) arcos.
    * O LKH resolve com TYPE : ATSP (transformação interna para TSP simétrico).
    * O regret é rotulado POR ARCO: fixar o arco (i, j) é diferente de fixar
      (j, i). A fixação usa FIXED_EDGES_SECTION quando o LKH respeita a
      direção; caso contrário, cai para o mascaramento da matriz (forçar o
      sucessor de i a ser j e o predecessor de j a ser i com custos BIG) e o
      custo é recalculado com a matriz original.

Uso:
    python generate_data.py                 # todos os tamanhos padrão
    python generate_data.py --sizes 5 10    # apenas alguns tamanhos
Reexecutar retoma de onde parou (instâncias .pkl existentes não são refeitas).
"""

import argparse
import itertools
import os
import pickle
import random
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import networkx as nx
import numpy as np
from sklearn.preprocessing import MinMaxScaler

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# (n_train, n_val) por tamanho de instância. A rotulagem do ATSP é ~2x mais
# cara que a do TSP (n(n-1) arcos em vez de n(n-1)/2 arestas, e o LKH trabalha
# internamente com dimensão 2n), por isso os tamanhos grandes usam menos
# instâncias que na versão simétrica.
DATASET_SPEC = {
    5:   (100, 20),
    10:  (100, 20),
    20:  (100, 20),
    50:  (40, 8),
    100: (24, 6),
}

# Seeds de treino começam aqui; benchmark usa seeds 1..20 (sem vazamento).
TRAIN_SEED_BASE = 10_000

# Custo proibitivo usado no mascaramento de matriz (>> n * dist_max ~ 2e5).
BIG_COST = 10 ** 6


# ------------------------------------------------------------------
# Mesma geração de matriz do benchmark (NewATSPs.py)
# ------------------------------------------------------------------
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


# ------------------------------------------------------------------
# LKH via subprocess (TSPLIB TYPE: ATSP) + fixação de arco direcionado
# ------------------------------------------------------------------
def find_lkh_binary():
    env = os.environ.get("LKH_BINARY")
    if env and os.path.exists(env):
        return env

    repo_root = os.path.dirname(SCRIPT_DIR)
    algo_dir = os.path.join(repo_root, "Algo comparison")
    for name in ("LKH.exe", "LKH"):
        candidate = os.path.join(algo_dir, name)
        if os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(
        "Binário do LKH não encontrado. Esperado 'Algo comparison/LKH.exe' "
        "(ou 'LKH'), ou defina a variável de ambiente LKH_BINARY."
    )


def solve_lkh(distance_matrix, seed, lkh_path, runs=1, fixed_edge=None):
    """Resolve o ATSP com o LKH. `fixed_edge=(i, j)` fixa o arco via TSPLIB.

    Retorna o tour aberto (lista de n nós, 0-indexado, começando no nó 0).
    A direção do tour retornado é significativa (custo assimétrico).
    """
    n = len(distance_matrix)

    with tempfile.TemporaryDirectory(prefix="lkh_gnn_") as tmp:
        tsp_file = os.path.join(tmp, "prob.atsp")
        par_file = os.path.join(tmp, "prob.par")
        tour_file = os.path.join(tmp, "prob.tour")

        with open(tsp_file, "w") as f:
            f.write("NAME : gnn_data\n")
            f.write("TYPE : ATSP\n")
            f.write(f"DIMENSION : {n}\n")
            f.write("EDGE_WEIGHT_TYPE : EXPLICIT\n")
            f.write("EDGE_WEIGHT_FORMAT : FULL_MATRIX\n")
            f.write("EDGE_WEIGHT_SECTION\n")
            for row in distance_matrix:
                f.write(" ".join(map(str, (int(v) for v in row))) + "\n")
            if fixed_edge is not None:
                f.write("FIXED_EDGES_SECTION\n")
                f.write(f"{fixed_edge[0] + 1} {fixed_edge[1] + 1}\n")
                f.write("-1\n")
            f.write("EOF\n")

        with open(par_file, "w") as f:
            f.write(f"PROBLEM_FILE = {tsp_file}\n")
            f.write(f"OUTPUT_TOUR_FILE = {tour_file}\n")
            f.write(f"SEED = {seed}\n")
            f.write(f"RUNS = {runs}\n")
            f.write("TRACE_LEVEL = 0\n")

        subprocess.run([lkh_path, par_file], capture_output=True, text=True, check=True)

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
        raise RuntimeError("Falha ao ler o tour do LKH.")

    start = tour.index(0)
    return tour[start:] + tour[:start]


def tour_has_arc(tour, arc):
    """True se o arco direcionado (i, j) aparece no tour FECHADO implícito."""
    i, j = arc
    n = len(tour)
    for k in range(n):
        if tour[k] == i and tour[(k + 1) % n] == j:
            return True
    return False


# Só para não repetir o aviso a cada fallback (threads podem imprimir 2x, ok).
_WARNED_FIXED_DIR = {"done": False}


def solve_lkh_forced_arc(distance_matrix, seed, lkh_path, arc):
    """Resolve o ATSP forçando o arco direcionado `arc = (i, j)` na solução.

    Tenta FIXED_EDGES_SECTION e verifica a direção no tour retornado (o LKH a
    respeita na grande maioria das chamadas, mas não em todas); quando a
    verificação falha, usa o mascaramento de matriz: o sucessor de i deve ser
    j e o predecessor de j deve ser i (demais alternativas custam BIG_COST).
    O custo do tour deve SEMPRE ser recalculado com a matriz original.
    """
    i, j = arc

    tour = solve_lkh(distance_matrix, seed, lkh_path, runs=1, fixed_edge=arc)
    if tour_has_arc(tour, arc):
        return tour

    if not _WARNED_FIXED_DIR["done"]:
        _WARNED_FIXED_DIR["done"] = True
        print("  [aviso] FIXED_EDGES_SECTION nem sempre respeita a direção do "
              "arco; esses casos usam o mascaramento de matriz (fallback).", flush=True)

    masked = np.array(distance_matrix, dtype=np.int64).copy()
    original = int(masked[i, j])
    masked[i, :] = BIG_COST
    masked[:, j] = BIG_COST
    masked[i, j] = original
    np.fill_diagonal(masked, 0)

    tour = solve_lkh(masked, seed, lkh_path, runs=1)
    if not tour_has_arc(tour, arc):
        raise RuntimeError(f"Mascaramento não forçou o arco {arc} no tour {tour}.")
    return tour


def closed_tour_cost(distance_matrix, tour):
    n = len(tour)
    return int(sum(distance_matrix[tour[i]][tour[(i + 1) % n]] for i in range(n)))


# ------------------------------------------------------------------
# Construção e rotulagem de uma instância
# ------------------------------------------------------------------
def build_instance_graph(distance_matrix):
    n = len(distance_matrix)
    G = nx.DiGraph()
    G.add_nodes_from(range(n))
    for i, j in itertools.permutations(range(n), 2):
        G.add_edge(i, j, weight=float(distance_matrix[i][j]))
    return G


def label_instance(G, distance_matrix, seed, lkh_path, runs_opt=2, workers=8):
    """Adiciona 'in_solution' e 'regret' a cada arco de G (in-place)."""
    opt_tour = solve_lkh(distance_matrix, seed, lkh_path, runs=runs_opt)
    opt_cost = closed_tour_cost(distance_matrix, opt_tour)

    closed = opt_tour + [opt_tour[0]]
    tour_arcs = set(zip(closed[:-1], closed[1:]))  # arcos DIRECIONADOS

    for e in G.edges:
        G.edges[e]['in_solution'] = e in tour_arcs
        G.edges[e]['regret'] = 0.0

    to_label = [e for e in G.edges if not G.edges[e]['in_solution']]

    def arc_regret(e):
        tour = solve_lkh_forced_arc(distance_matrix, seed, lkh_path, e)
        cost = closed_tour_cost(distance_matrix, tour)
        return max(0.0, (cost - opt_cost) / opt_cost)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        regrets = list(ex.map(arc_regret, to_label))

    for e, r in zip(to_label, regrets):
        G.edges[e]['regret'] = r

    return G


# ------------------------------------------------------------------
# Pipeline por tamanho: instâncias -> split -> scalers
# ------------------------------------------------------------------
def generate_size(n, n_train, n_val, data_dir, lkh_path, runs_opt, workers):
    out_dir = os.path.join(data_dir, f"atsp{n}")
    os.makedirs(out_dir, exist_ok=True)

    names = []
    total = n_train + n_val
    for i in range(total):
        seed = TRAIN_SEED_BASE + i
        fname = f"atsp{n}_seed{seed}.pkl"
        fpath = os.path.join(out_dir, fname)
        names.append(fname)

        if os.path.exists(fpath):
            continue

        t0 = time.perf_counter()
        D = generate_asymmetric_distance_matrix(n, seed)
        G = build_instance_graph(D)
        label_instance(G, D, seed, lkh_path, runs_opt=runs_opt, workers=workers)
        with open(fpath, "wb") as f:
            pickle.dump(G, f)
        print(f"  [atsp{n}] instância {i + 1}/{total} (seed {seed}) "
              f"rotulada em {time.perf_counter() - t0:.1f}s", flush=True)

    train_files, val_files = names[:n_train], names[n_train:]
    for file_list, list_name in ((train_files, "train.txt"), (val_files, "val.txt")):
        with open(os.path.join(out_dir, list_name), "w") as f:
            f.write("\n".join(file_list) + "\n")

    # Scalers MinMax ajustados APENAS no conjunto de treino (como no original).
    scalers = {'weight': MinMaxScaler(), 'regret': MinMaxScaler()}
    for fname in train_files:
        with open(os.path.join(out_dir, fname), "rb") as f:
            G = pickle.load(f)
        for k in scalers:
            scalers[k].partial_fit(np.vstack([G.edges[e][k] for e in G.edges]))
    with open(os.path.join(out_dir, "scalers.pkl"), "wb") as f:
        pickle.dump(scalers, f)

    print(f"[atsp{n}] concluído: {n_train} treino + {n_val} val em {out_dir}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Gera dados de treino do GNN ATSP (labels de regret via LKH).")
    parser.add_argument("--sizes", type=int, nargs="+", default=sorted(DATASET_SPEC),
                        help="Tamanhos de instância a gerar (padrão: todos).")
    parser.add_argument("--data-dir", type=str, default=os.path.join(SCRIPT_DIR, "data"))
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4)),
                        help="Execuções paralelas do LKH na rotulagem.")
    parser.add_argument("--runs-opt", type=int, default=2,
                        help="RUNS do LKH para o tour ótimo de referência.")
    args = parser.parse_args()

    lkh_path = find_lkh_binary()
    print(f"LKH: {lkh_path}")
    print(f"Workers: {args.workers}\n")

    for n in args.sizes:
        if n not in DATASET_SPEC:
            raise ValueError(f"Tamanho {n} sem spec definida em DATASET_SPEC.")
        n_train, n_val = DATASET_SPEC[n]
        t0 = time.perf_counter()
        generate_size(n, n_train, n_val, args.data_dir, lkh_path, args.runs_opt, args.workers)
        print(f"[atsp{n}] tempo total: {(time.perf_counter() - t0) / 60:.1f} min\n", flush=True)


if __name__ == "__main__":
    main()
