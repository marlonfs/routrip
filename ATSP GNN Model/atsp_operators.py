"""
Operadores de busca local para o ATSP — adaptados de "GNN Model/gnn_operators.py"
(originalmente de https://github.com/walidgeuttala/atsp, src/utils/operators.py).

O 2-opt clássico REVERTE um segmento do tour; em matrizes assimétricas o custo
do segmento revertido muda (D[a][b] != D[b][a]), então o delta simétrico do
original é inválido. Ele foi substituído pelo Or-opt: relocação de um segmento
de comprimento L (2 ou 3) SEM reversão — todos os arcos preservam a direção,
e o delta usa apenas acessos orientados. O relocate (equivalente a Or-opt com
L = 1) já era direcionalmente correto e foi mantido sem alterações.

Convenção (igual ao original): `tour` é uma lista FECHADA — o depósito aparece
na primeira e na última posição.
"""

import itertools
import numpy as np


# ------------------------------------------------------------------
# Or-opt: move um segmento de L nós sem reverter (válido para ATSP)
# ------------------------------------------------------------------
def or_opt(tour, i, L, j):
    """Remove o segmento tour[i:i+L] e o reinsere na posição j da lista restante."""
    seg = tour[i:i + L]
    rest = tour[:i] + tour[i + L:]
    return rest[:j] + seg + rest[j:]


def or_opt_cost(tour, D, i, L, j):
    """Delta de custo do or_opt(tour, i, L, j); j indexa a lista SEM o segmento."""
    if j == i:
        return 0

    a = tour[i - 1]
    s0 = tour[i]
    s1 = tour[i + L - 1]
    c = tour[i + L]
    d = tour[j - 1] if j - 1 < i else tour[j - 1 + L]
    e = tour[j] if j < i else tour[j + L]

    delta = -D[a, s0] \
            - D[s1, c] \
            + D[a, c] \
            - D[d, e] \
            + D[d, s0] \
            + D[s1, e]
    return delta


def or_opt_a2a(tour, D, first_improvement=False, segment_lengths=(2, 3)):
    best_move = None
    best_delta = 0

    m = len(tour)
    for L in segment_lengths:
        for i, j in itertools.product(range(1, m - L), range(1, m - L)):
            if i == j:
                continue

            delta = or_opt_cost(tour, D, i, L, j)
            if delta < best_delta and not np.isclose(0, delta):
                best_delta = delta
                best_move = i, L, j
                if first_improvement:
                    break
        if first_improvement and best_move is not None:
            break

    if best_move is not None:
        return best_delta, or_opt(tour, *best_move)
    return 0, tour


def or_opt_o2a(tour, D, i, first_improvement=False, segment_lengths=(2, 3)):
    assert i > 0 and i < len(tour) - 1

    best_move = None
    best_delta = 0

    m = len(tour)
    for L in segment_lengths:
        # segmentos que CONTÊM a posição i (o nó penalizado participa do movimento)
        for s in range(max(1, i - L + 1), min(i, m - 1 - L) + 1):
            for j in range(1, m - L):
                if j == s:
                    continue

                delta = or_opt_cost(tour, D, s, L, j)
                if delta < best_delta and not np.isclose(0, delta):
                    best_delta = delta
                    best_move = s, L, j
                    if first_improvement:
                        break
            if first_improvement and best_move is not None:
                break
        if first_improvement and best_move is not None:
            break

    if best_move is not None:
        return best_delta, or_opt(tour, *best_move)
    return 0, tour


# ------------------------------------------------------------------
# Relocate (Or-opt com L = 1) — inalterado, já é válido para ATSP
# ------------------------------------------------------------------
def relocate(tour, i, j):
    new_tour = tour.copy()
    n = new_tour.pop(i)
    new_tour.insert(j, n)
    return new_tour


def relocate_cost(tour, D, i, j):
    if i == j:
        return 0

    a = tour[i - 1]
    b = tour[i]
    c = tour[i + 1]
    if i < j:
        d = tour[j]
        e = tour[j + 1]
    else:
        d = tour[j - 1]
        e = tour[j]

    delta = -D[a, b] \
            - D[b, c] \
            + D[a, c] \
            - D[d, e] \
            + D[d, b] \
            + D[b, e]
    return delta


def relocate_o2a(tour, D, i, first_improvement=False):
    assert i > 0 and i < len(tour) - 1

    best_move = None
    best_delta = 0

    idxs = range(1, len(tour) - 1)
    for j in idxs:
        if i == j:
            continue

        delta = relocate_cost(tour, D, i, j)
        if delta < best_delta and not np.isclose(0, delta):
            best_delta = delta
            best_move = i, j
            if first_improvement:
                break

    if best_move is not None:
        return best_delta, relocate(tour, *best_move)
    return 0, tour


def relocate_a2a(tour, D, first_improvement=False):
    best_move = None
    best_delta = 0

    idxs = range(1, len(tour) - 1)
    for i, j in itertools.permutations(idxs, 2):
        if i - j == 1:  # e.g. relocate 2 -> 3 == relocate 3 -> 2
            continue

        delta = relocate_cost(tour, D, i, j)
        if delta < best_delta and not np.isclose(0, delta):
            best_delta = delta
            best_move = i, j
            if first_improvement:
                break

    if best_move is not None:
        return best_delta, relocate(tour, *best_move)
    return 0, tour
