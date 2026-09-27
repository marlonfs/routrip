import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from itertools import permutations
from typing import Literal

from core.paths import lkh_path

UNREACHABLE = 9_999_999

# Até aqui a frota é resolvida de forma exata (Held-Karp + partição por subconjuntos,
# ~3^k): 12 paradas custam ≤ 0,4 s, contra os ~8 s do LKH — que ainda erraria o ótimo
# em ~1 de cada 10 instâncias desse tamanho.
EXACT_MAX_STOPS = 12

MtspObjective = Literal["minmax", "minsum"]


def _weight(value) -> int:
    if value is None:
        return UNREACHABLE
    return max(0, round(value))


def _int_matrix(matrix: list[list[float]], service: int = 0) -> list[list[int]]:
    """`service` entra em todo arco que chega numa parada (j ≠ 0): assim o custo de
    uma rota é direção + atendimento, e é esse o tempo que o MINMAX tem de encurtar."""
    n = len(matrix)
    return [[0 if i == j else _weight(matrix[i][j]) + (service if j != 0 else 0)
             for j in range(n)] for i in range(n)]


def _tour_cost(matrix: list[list[int]], tour: list[int]) -> int:
    total = 0
    for k in range(len(tour)):
        total += matrix[tour[k]][tour[(k + 1) % len(tour)]]
    return total


def _brute_force(matrix: list[list[int]]) -> list[int]:
    n = len(matrix)
    best, best_cost = None, None
    for perm in permutations(range(1, n)):
        tour = [0, *perm]
        cost = _tour_cost(matrix, tour)
        if best_cost is None or cost < best_cost:
            best, best_cost = tour, cost
    return best


def _write_problem(path: str, ints: list[list[int]]) -> None:
    with open(path, "w", encoding="ascii") as f:
        f.write("NAME : routrip\n")
        f.write("TYPE : ATSP\n")
        f.write(f"DIMENSION : {len(ints)}\n")
        f.write("EDGE_WEIGHT_TYPE : EXPLICIT\n")
        f.write("EDGE_WEIGHT_FORMAT : FULL_MATRIX\n")
        f.write("EDGE_WEIGHT_SECTION\n")
        for row in ints:
            f.write(" ".join(str(w) for w in row) + "\n")
        f.write("EOF\n")


def _run_lkh(par_file: str, expected_output: str) -> None:
    lkh = lkh_path()
    if not lkh.is_file():
        raise RuntimeError(f"Binário do LKH não encontrado em {lkh}")
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(
        [str(lkh), par_file],
        capture_output=True, text=True, creationflags=creationflags,
    )
    if result.returncode != 0 or not os.path.isfile(expected_output):
        raise RuntimeError(
            f"LKH falhou (código {result.returncode}): {result.stderr or result.stdout}"
        )


def solve_atsp(matrix: list[list[float]], seed: int = 42, runs: int = 4,
               time_limit_s: float = 10.0) -> list[int]:
    """Resolve o ATSP com LKH-3; retorna o tour 0-indexado começando no nó 0."""
    n = len(matrix)
    if n <= 2:
        return list(range(n))

    ints = _int_matrix(matrix)
    if n <= 4:
        return _brute_force(ints)

    with tempfile.TemporaryDirectory(prefix="routrip_lkh_") as tmp:
        atsp_file = os.path.join(tmp, "problem.atsp")
        par_file = os.path.join(tmp, "problem.par")
        tour_file = os.path.join(tmp, "problem.tour")

        _write_problem(atsp_file, ints)
        with open(par_file, "w", encoding="ascii") as f:
            f.write(f"PROBLEM_FILE = {atsp_file}\n")
            f.write(f"OUTPUT_TOUR_FILE = {tour_file}\n")
            f.write(f"SEED = {seed}\n")
            f.write(f"RUNS = {runs}\n")
            f.write(f"TIME_LIMIT = {time_limit_s}\n")
            f.write("TRACE_LEVEL = 0\n")

        _run_lkh(par_file, tour_file)

        tour: list[int] = []
        with open(tour_file, "r", encoding="ascii") as f:
            in_section = False
            for line in f:
                line = line.strip()
                if line.startswith("TOUR_SECTION"):
                    in_section = True
                    continue
                if in_section:
                    if line in ("-1", "EOF"):
                        break
                    tour.append(int(line) - 1)

    if sorted(tour) != list(range(n)):
        raise RuntimeError("Tour inválido retornado pelo LKH")
    start = tour.index(0)
    return tour[start:] + tour[:start]


def route_costs(matrix: list[list[int]], routes: list[list[int]]) -> list[int]:
    """Custo de cada rota fechada (depósito → paradas → depósito)."""
    return [_tour_cost(matrix, [0, *r]) for r in routes]


def _exact_mtsp(ints: list[list[int]], m: int, objective: MtspObjective) -> list[list[int]]:
    """Ótimo exato para poucas paradas. Held-Karp dá o melhor ciclo pelo depósito de
    cada subconjunto de paradas; depois uma DP de partição escolhe m subconjuntos
    disjuntos e não vazios que cobrem todas, minimizando o máximo ou a soma."""
    k = len(ints) - 1
    full = (1 << k) - 1
    inf = float("inf")

    # dp[S][j]: saindo do depósito, visitou S e está na parada j (j ∈ S)
    dp = [[inf] * k for _ in range(1 << k)]
    parent = [[-1] * k for _ in range(1 << k)]
    for j in range(k):
        dp[1 << j][j] = ints[0][j + 1]
    for s in range(1, 1 << k):
        for j in range(k):
            cur = dp[s][j]
            if cur == inf or not (s >> j) & 1:
                continue
            for nxt in range(k):
                if (s >> nxt) & 1:
                    continue
                t = s | (1 << nxt)
                cand = cur + ints[j + 1][nxt + 1]
                if cand < dp[t][nxt]:
                    dp[t][nxt] = cand
                    parent[t][nxt] = j

    cycle = [inf] * (1 << k)
    last = [-1] * (1 << k)
    for s in range(1, 1 << k):
        for j in range(k):
            if (s >> j) & 1 and dp[s][j] != inf:
                c = dp[s][j] + ints[j + 1][0]
                if c < cycle[s]:
                    cycle[s], last[s] = c, j

    def combine(a, b):
        return max(a, b) if objective == "minmax" else a + b

    # best[p][S]: melhor valor cobrindo S com exatamente p rotas
    best = [dict() for _ in range(m + 1)]
    choice = [dict() for _ in range(m + 1)]
    best[0][0] = 0
    for p in range(1, m + 1):
        for s in range(1, full + 1):
            if bin(s).count("1") < p:
                continue
            low = s & -s
            rest_all = s ^ low
            # T contém a menor parada de S, para não contar a mesma partição várias vezes
            sub = rest_all
            best_val, best_t = inf, 0
            while True:
                t = sub | low
                rem = s ^ t
                prev = best[p - 1].get(rem)
                if prev is not None:
                    v = combine(prev, cycle[t]) if p > 1 else cycle[t]
                    if v < best_val:
                        best_val, best_t = v, t
                if sub == 0:
                    break
                sub = (sub - 1) & rest_all
            if best_val != inf:
                best[p][s] = best_val
                choice[p][s] = best_t

    routes: list[list[int]] = []
    s = full
    for p in range(m, 0, -1):
        t = choice[p][s]
        path, j, cur = [], last[t], t
        while j != -1:
            path.append(j + 1)
            pj = parent[cur][j]
            cur ^= 1 << j
            j = pj
        routes.append(path[::-1])
        s ^= t
    return routes


def _parse_mtsp_solution(path: str) -> list[list[int]]:
    """Linhas do MTSP_SOLUTION_FILE: `1 4 10 7 1 (#3)  Cost: 140`, 1-indexadas."""
    routes: list[list[int]] = []
    with open(path, "r", encoding="ascii") as f:
        for line in f:
            head = line.split("(#")[0].split()
            if len(head) < 2 or not all(tok.isdigit() for tok in head):
                continue
            nodes = [int(tok) - 1 for tok in head]
            if nodes[0] != 0 or nodes[-1] != 0:
                continue
            routes.append(nodes[1:-1])
    return routes


def _reorder(ints: list[list[int]], route: list[int], **lkh) -> list[int]:
    """Melhor ordem de uma rota isolada, resolvendo o ATSP da submatriz dela."""
    if len(route) <= 1:
        return route
    nodes = [0, *route]
    sub = [[ints[a][b] for b in nodes] for a in nodes]
    return [nodes[i] for i in solve_atsp(sub, **lkh)[1:]]


def _fill_empty(ints: list[list[int]], routes: list[list[int]], m: int,
                objective: MtspObjective) -> list[list[int]]:
    """O LKH-3 não impõe MTSP_MIN_SIZE no MINMAX e às vezes deixa veículo parado.
    Cada veículo vazio recebe a parada cuja saída de sua rota (mais a ida e volta
    dela sozinha) menos piora o objetivo; a rota que a cedeu é reordenada."""
    routes = [r for r in routes if r]
    while len(routes) < m:
        best = None
        for ri, r in enumerate(routes):
            if len(r) < 2:
                continue
            for pos in range(len(r)):
                cand = [x for x in routes]
                cand[ri] = r[:pos] + r[pos + 1:]
                cand.append([r[pos]])
                c = route_costs(ints, cand)
                val = max(c) if objective == "minmax" else sum(c)
                if best is None or val < best[0]:
                    best = (val, ri, cand)
        _, ri, routes = best
        routes[ri] = _reorder(ints, routes[ri], runs=1, time_limit_s=2.0)
    return routes


def _key(ints: list[list[int]], routes: list[list[int]],
         objective: MtspObjective) -> tuple[int, int]:
    """Objetivo com desempate: no MINMAX, entre duas frotas que terminam na mesma hora
    vence a que roda menos; no MINSUM, entre somas iguais vence a mais equilibrada."""
    c = route_costs(ints, routes)
    return (max(c), sum(c)) if objective == "minmax" else (sum(c), max(c))


def _relocate(ints: list[list[int]], routes: list[list[int]],
              objective: MtspObjective, max_moves: int = 2000) -> list[list[int]]:
    """Busca local entre rotas: tira uma parada de uma rota e a encaixa na melhor
    posição de outra, enquanto isso melhorar o objetivo. O MINMAX do LKH-3 converge
    devagar e em 5–10 s ainda deixa trocas óbvias desse tipo para trás."""
    routes = [list(r) for r in routes]
    costs = route_costs(ints, routes)

    def key(cs):
        return (max(cs), sum(cs)) if objective == "minmax" else (sum(cs), max(cs))

    current = key(costs)
    for _ in range(max_moves):
        best = None
        for ri, r in enumerate(routes):
            if len(r) < 2:
                continue
            full_r = [0, *r, 0]
            for p in range(1, len(full_r) - 1):
                a, s, b = full_r[p - 1], full_r[p], full_r[p + 1]
                rem = ints[a][b] - ints[a][s] - ints[s][b]
                for qi, q in enumerate(routes):
                    if qi == ri:
                        continue
                    full_q = [0, *q, 0]
                    for t in range(len(full_q) - 1):
                        x, y = full_q[t], full_q[t + 1]
                        ins = ints[x][s] + ints[s][y] - ints[x][y]
                        cs = list(costs)
                        cs[ri] += rem
                        cs[qi] += ins
                        k = key(cs)
                        if k < current and (best is None or k < best[0]):
                            best = (k, ri, p - 1, qi, t, cs)
        if best is None:
            break
        current, ri, p, qi, t, costs = best
        s = routes[ri].pop(p)
        routes[qi].insert(t, s)
    return routes


def _improve(ints: list[list[int]], routes: list[list[int]],
             objective: MtspObjective) -> list[list[int]]:
    """Alterna realocação entre rotas e reordenação de cada rota até parar de ganhar."""
    best = routes
    best_key = _key(ints, routes, objective)
    for _ in range(4):
        cand = _relocate(ints, best, objective)
        cand = [_reorder(ints, r, runs=1, time_limit_s=2.0) for r in cand]
        k = _key(ints, cand, objective)
        if k >= best_key:
            break
        best, best_key = cand, k
    return best


def _lkh_mtsp(ints: list[list[int]], m: int, objective: MtspObjective,
              seed: int, time_limit_s: float) -> list[list[int]]:
    with tempfile.TemporaryDirectory(prefix="routrip_lkh_") as tmp:
        atsp_file = os.path.join(tmp, "problem.atsp")
        par_file = os.path.join(tmp, "problem.par")
        tour_file = os.path.join(tmp, "problem.tour")
        sol_file = os.path.join(tmp, "problem.sol")

        _write_problem(atsp_file, ints)
        with open(par_file, "w", encoding="ascii") as f:
            f.write(f"PROBLEM_FILE = {atsp_file}\n")
            f.write(f"OUTPUT_TOUR_FILE = {tour_file}\n")
            f.write(f"MTSP_SOLUTION_FILE = {sol_file}\n")
            f.write(f"SALESMEN = {m}\n")
            f.write("DEPOT = 1\n")
            f.write(f"MTSP_OBJECTIVE = {objective.upper()}\n")
            f.write("MTSP_MIN_SIZE = 1\n")
            f.write(f"SEED = {seed}\n")
            f.write("RUNS = 1\n")
            f.write(f"TIME_LIMIT = {time_limit_s}\n")
            f.write("TRACE_LEVEL = 0\n")

        _run_lkh(par_file, sol_file)
        return _parse_mtsp_solution(sol_file)


def solve_mtsp(matrix: list[list[float]], vehicles: int,
               objective: MtspObjective = "minmax", service_s: int = 0,
               seed: int = 42, runs: int = 4,
               time_limit_s: float = 8.0) -> list[list[int]]:
    """Divide as paradas entre `vehicles` veículos que saem e voltam ao nó 0.

    Devolve uma lista de rotas, cada uma com as paradas na ordem de visita (índices da
    matriz, sem o depósito). Todo veículo usado recebe ao menos uma parada; com menos
    paradas que veículos, só `n - 1` rotas saem. `minmax` encurta a rota mais longa (o
    último a voltar); `minsum` encurta a soma de todas.

    As `runs` tentativas do LKH rodam em paralelo, cada uma com sua semente e uma run
    só: `TIME_LIMIT` vale por run, então em sequência 4 runs custariam 4× o tempo."""
    n = len(matrix)
    if n <= 1:
        return []
    m = max(1, min(vehicles, n - 1))
    if m == 1:
        return [solve_atsp(matrix, seed=seed, runs=runs)[1:]]

    ints = _int_matrix(matrix, service_s)
    if n - 1 <= EXACT_MAX_STOPS:
        routes = _exact_mtsp(ints, m, objective)
    else:
        workers = max(1, min(runs, os.cpu_count() or 1))
        with ThreadPoolExecutor(workers) as pool:
            results = list(pool.map(
                lambda sd: _lkh_mtsp(ints, m, objective, sd, time_limit_s),
                [seed + i for i in range(workers)],
            ))
        cands = [_fill_empty(ints, r, m, objective) for r in results]
        routes = min(cands, key=lambda r: _key(ints, r, objective))
        routes = _improve(ints, routes, objective)

    visited = sorted(i for r in routes for i in r)
    if len(routes) != m or any(not r for r in routes) or visited != list(range(1, n)):
        raise RuntimeError("Divisão inválida das paradas retornada pelo LKH")
    return routes
