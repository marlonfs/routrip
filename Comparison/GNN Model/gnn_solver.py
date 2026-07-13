"""
Solver GNN para o comparativo — inferência adaptada de
https://github.com/walidgeuttala/atsp (src/test.py).

Pipeline por instância (igual ao test.py original):
    1. Constrói o line graph da instância (cacheado por tamanho) e escala os
       pesos das arestas com os scalers do treino;
    2. O GNN prediz o regret de cada aresta (regret_pred, truncado em >= 0);
    3. Tour inicial: Nearest-Neighbor guiado por regret_pred;
    4. Melhoria: Guided Local Search (guia = regret_pred) até o limite de tempo.

Requer os checkpoints treinados por train_gnn.py em checkpoints/tsp{n}/.
"""

import json
import itertools
import os
import pickle
import time

import networkx as nx
import numpy as np
import torch
from torch_geometric.utils import from_networkx

from gnn_model import build_model
from gnn_algorithms import nearest_neighbor, tour_cost, guided_local_search

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CHECKPOINT_DIR = os.path.join(SCRIPT_DIR, "checkpoints")

# Orçamento de tempo (s) do Guided Local Search por tamanho de instância.
GLS_TIME_LIMITS = {5: 0.5, 10: 1.0, 20: 2.0, 50: 5.0, 100: 10.0}

_BUNDLE_CACHE = {}   # n -> (model, scalers)
_LG_CACHE = {}       # n -> (edge_index, mapping)


def _load_bundle(n, checkpoint_dir):
    key = (n, checkpoint_dir)
    if key in _BUNDLE_CACHE:
        return _BUNDLE_CACHE[key]

    ckpt_dir = os.path.join(checkpoint_dir, f"tsp{n}")
    params_path = os.path.join(ckpt_dir, "params.json")
    if not os.path.exists(params_path):
        raise FileNotFoundError(
            f"Checkpoint do GNN para n={n} não encontrado em '{ckpt_dir}'. "
            f"Treine antes com: python \"GNN Model/train_gnn.py\" --sizes {n}"
        )

    params = json.load(open(params_path))
    model = build_model(params)
    checkpoint = torch.load(os.path.join(ckpt_dir, "checkpoint_best_val.pt"),
                            map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()

    scalers = pickle.load(open(os.path.join(ckpt_dir, "scalers.pkl"), "rb"))
    if 'edges' in scalers:
        scalers = scalers['edges']

    _BUNDLE_CACHE[key] = (model, scalers)
    return model, scalers


def _line_graph(n):
    """Line graph do K_n completo (estrutura idêntica para qualquer instância de tamanho n)."""
    if n in _LG_CACHE:
        return _LG_CACHE[n]

    G = nx.Graph()
    G.add_nodes_from(range(n))
    G.add_edges_from(itertools.combinations(range(n), 2))
    lG = nx.line_graph(G)
    data = from_networkx(lG)
    mapping = list(lG.nodes())

    _LG_CACHE[n] = (data.edge_index, mapping)
    return _LG_CACHE[n]


def solve_gnn(distance_matrix, seed, time_limit=None, perturbation_moves=20,
              checkpoint_dir=DEFAULT_CHECKPOINT_DIR):
    """Resolve o TSP com GNN (regret_pred) + Guided Local Search.

    Retorna o tour aberto (lista de n nós, começando no nó 0). O `seed` não é
    usado (todo o pipeline de inferência é determinístico), mas é mantido na
    assinatura por consistência com os demais solvers do comparativo.
    """
    n = len(distance_matrix)
    if time_limit is None:
        time_limit = GLS_TIME_LIMITS.get(n, 10.0)

    model, scalers = _load_bundle(n, checkpoint_dir)
    edge_index, mapping = _line_graph(n)

    # 1-2. Predição do regret de cada aresta
    weights = np.array([[float(distance_matrix[u][v])] for (u, v) in mapping])
    x = torch.tensor(scalers['weight'].transform(weights), dtype=torch.float32)
    with torch.no_grad():
        y_pred = model(x, edge_index)
    regret_pred = scalers['regret'].inverse_transform(y_pred.numpy())

    G = nx.Graph()
    G.add_nodes_from(range(n))
    for idx, (u, v) in enumerate(mapping):
        G.add_edge(u, v,
                   weight=float(distance_matrix[u][v]),
                   regret_pred=max(regret_pred[idx].item(), 0.0))

    # 3. Tour inicial guiado pelo regret previsto
    init_tour = nearest_neighbor(G, 0, weight='regret_pred')
    init_cost = tour_cost(G, init_tour, weight='weight')

    # 4. Guided Local Search com o regret previsto como guia
    best_tour, _, _, _ = guided_local_search(
        G, init_tour, init_cost, time.time() + time_limit,
        weight='weight', guides=['regret_pred'],
        perturbation_moves=perturbation_moves, first_improvement=False,
    )

    return best_tour[:-1]  # remove o retorno ao depósito (tour aberto)
