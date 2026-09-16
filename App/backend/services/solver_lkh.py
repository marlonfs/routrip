import os
import subprocess
import sys
import tempfile
from itertools import permutations

from core.paths import lkh_path

UNREACHABLE = 9_999_999


def _weight(value) -> int:
    if value is None:
        return UNREACHABLE
    return max(0, round(value))


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


def solve_atsp(matrix: list[list[float]], seed: int = 42, runs: int = 4,
               time_limit_s: float = 10.0) -> list[int]:
    """Resolve o ATSP com LKH-3; retorna o tour 0-indexado começando no nó 0."""
    n = len(matrix)
    if n <= 2:
        return list(range(n))

    ints = [[0 if i == j else _weight(matrix[i][j]) for j in range(n)] for i in range(n)]
    if n <= 4:
        return _brute_force(ints)

    lkh = lkh_path()
    if not lkh.is_file():
        raise RuntimeError(f"Binário do LKH não encontrado em {lkh}")

    with tempfile.TemporaryDirectory(prefix="routrip_lkh_") as tmp:
        atsp_file = os.path.join(tmp, "problem.atsp")
        par_file = os.path.join(tmp, "problem.par")
        tour_file = os.path.join(tmp, "problem.tour")

        with open(atsp_file, "w", encoding="ascii") as f:
            f.write("NAME : routrip\n")
            f.write("TYPE : ATSP\n")
            f.write(f"DIMENSION : {n}\n")
            f.write("EDGE_WEIGHT_TYPE : EXPLICIT\n")
            f.write("EDGE_WEIGHT_FORMAT : FULL_MATRIX\n")
            f.write("EDGE_WEIGHT_SECTION\n")
            for row in ints:
                f.write(" ".join(str(w) for w in row) + "\n")
            f.write("EOF\n")

        with open(par_file, "w", encoding="ascii") as f:
            f.write(f"PROBLEM_FILE = {atsp_file}\n")
            f.write(f"OUTPUT_TOUR_FILE = {tour_file}\n")
            f.write(f"SEED = {seed}\n")
            f.write(f"RUNS = {runs}\n")
            f.write(f"TIME_LIMIT = {time_limit_s}\n")
            f.write("TRACE_LEVEL = 0\n")

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            [str(lkh), par_file],
            capture_output=True, text=True, creationflags=creationflags,
        )
        if result.returncode != 0 or not os.path.isfile(tour_file):
            raise RuntimeError(
                f"LKH falhou (código {result.returncode}): {result.stderr or result.stdout}"
            )

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
