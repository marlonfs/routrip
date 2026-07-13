"""
Algoritmos de construção e busca (Nearest-Neighbor guiado + Guided Local Search)
— adaptados de https://github.com/walidgeuttala/atsp (src/algorithms.py).

Única mudança em relação ao original: `tour_cost`/`tour_cost2` foram trazidos
para este módulo (no repositório original viviam em utils/__init__.py, que
puxa torch/lkh e outras dependências desnecessárias aqui).
"""

import time

import networkx as nx
import numpy as np

import gnn_operators as operators


def tour_cost(G, tour, weight='weight'):
    c = 0
    for e in zip(tour[:-1], tour[1:]):
        c += G.edges[e][weight]
    return c


def tour_cost2(tour, weight):
    c = 0
    for e in zip(tour[:-1], tour[1:]):
        c += weight[e]
    return c


def nearest_neighbor(G, depot, weight='weight'):
    tour = [depot]
    while len(tour) < len(G.nodes):
        i = tour[-1]
        neighbours = [(j, G.edges[(i, j)][weight]) for j in G.neighbors(i) if j not in tour]
        j, dist = min(neighbours, key=lambda e: e[1])
        tour.append(j)

    tour.append(depot)
    return tour


def local_search(init_tour, init_cost, D, first_improvement=False):
    cur_tour, cur_cost = init_tour, init_cost
    search_progress = []
    cnt = 0
    improved = True
    while improved and cnt < 100:

        improved = False
        for operator in [operators.two_opt_a2a, operators.relocate_a2a]:
            delta, new_tour = operator(cur_tour, D, first_improvement)
            delta = tour_cost2(new_tour, D) - cur_cost
            if delta < 0:
                improved = True
                cur_cost += delta
                cur_tour = new_tour
                search_progress.append({
                    'time': time.time(),
                    'cost': cur_cost
                })
            cnt += 1

    return cur_tour, cur_cost, search_progress, cnt


def guided_local_search(G, init_tour, init_cost, t_lim, weight='weight', guides=['weight'],
                        perturbation_moves=30, first_improvement=False):
    k = 0.1 * init_cost / len(G.nodes)
    nx.set_edge_attributes(G, 0, 'penalty')

    edge_weight, _ = nx.attr_matrix(G, weight)
    edge_weight = np.asarray(edge_weight)
    cnt_ans = 0
    cur_tour, cur_cost, search_progress, cnt = local_search(init_tour, init_cost, edge_weight, first_improvement)
    cnt_ans += cnt
    best_tour, best_cost = cur_tour, cur_cost
    iter_i = 0
    while time.time() < t_lim:
        guide = guides[iter_i % len(guides)]  # option change guide ever iteration (as in KGLS)

        # perturbation
        moves = 0
        cnt = 0
        while moves < perturbation_moves:
            # penalize edge
            max_util = 0
            max_util_e = None
            for e in zip(cur_tour[:-1], cur_tour[1:]):
                util = G[e[0]][e[1]][guide] / (1 + G[e[0]][e[1]]['penalty'])

                if util > max_util or max_util_e is None:
                    max_util = util
                    max_util_e = e
            G[max_util_e[0]][max_util_e[1]]['penalty'] += 1.
            edge_penalties, _ = nx.attr_matrix(G, 'penalty')
            edge_weight_guided = edge_weight + k * np.asarray(edge_penalties)
            # apply operator to edge
            for n in max_util_e:
                if n != 0:  # not the depot
                    i = cur_tour.index(n)

                    for operator in [operators.two_opt_o2a, operators.relocate_o2a]:
                        moved = False

                        delta, new_tour = operator(cur_tour, edge_weight_guided, i, first_improvement)
                        if delta < 0:
                            cur_cost = tour_cost(G, new_tour, weight)
                            cur_tour = new_tour
                            moved = True

                            search_progress.append({
                                'time': time.time(),
                                'cost': cur_cost
                            })
                        if moved == False:
                            cnt += 1
                            if cnt == 10:
                                moved = True
                                cnt = 0
                                search_progress.append({
                                    'time': time.time(),
                                    'cost': cur_cost
                                })
                        moves += moved
                        cnt_ans += 1

        # optimisation
        cur_tour, cur_cost, new_search_progress, cnt = local_search(cur_tour, cur_cost, edge_weight, first_improvement)
        search_progress += new_search_progress
        if cur_cost < best_cost:
            best_tour, best_cost = cur_tour, cur_cost

        iter_i += 1

    cnt_ans += cnt

    return best_tour, best_cost, search_progress, cnt_ans
