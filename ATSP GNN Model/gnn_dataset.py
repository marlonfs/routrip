"""
Dataset PyTorch para o treino do GNN ATSP — adaptado de
"GNN Model/gnn_dataset.py" (que adapta https://github.com/walidgeuttala/atsp).

Cada instância (grafo ATSP completo DIRECIONADO com 'weight' e 'regret' por
arco) é convertida no LINE GRAPH direcionado: cada arco (u, v) vira um nó, e
existe um arco (u, v) -> (v, w) no line graph quando o arco (v, w) continua o
caminho — exatamente a semântica de sequência de um tour direcionado. Como
todas as instâncias de um mesmo tamanho têm a mesma estrutura, o line graph é
construído uma única vez e reutilizado.
"""

import pathlib
import pickle

import networkx as nx
import torch
import torch.utils.data
from torch_geometric.utils import from_networkx


class ATSPDataset(torch.utils.data.Dataset):
    def __init__(self, instances_file, scalers_file=None):
        if not isinstance(instances_file, pathlib.Path):
            instances_file = pathlib.Path(instances_file)
        self.root_dir = instances_file.parent
        self.instances = sorted([line.strip() for line in open(instances_file) if line.strip()])
        if scalers_file is None:
            scalers_file = self.root_dir / 'scalers.pkl'
        scalers = pickle.load(open(scalers_file, 'rb'))
        if 'edges' in scalers:  # compatibilidade com formato antigo
            self.scalers = scalers['edges']
        else:
            self.scalers = scalers

        # só funciona para datasets homogêneos (mesmo n em todas as instâncias)
        with open(self.root_dir / self.instances[0], 'rb') as file:
            G = pickle.load(file)
        lG = nx.line_graph(G)
        self.G = from_networkx(lG)
        self.mapping = dict(zip(range(lG.number_of_nodes()), lG.nodes()))

    def __len__(self):
        return len(self.instances)

    def __getitem__(self, i):
        if torch.is_tensor(i):
            i = i.tolist()
        with open(self.root_dir / self.instances[i], 'rb') as file:
            G = pickle.load(file)

        return self.get_scaled_features(G)

    def get_scaled_features(self, G):
        weight = torch.tensor(
            [G[self.mapping[u][0]][self.mapping[u][1]]['weight'] for u in range(self.G.num_nodes)],
            dtype=torch.float32)
        regret = torch.tensor(
            [G[self.mapping[u][0]][self.mapping[u][1]]['regret'] for u in range(self.G.num_nodes)],
            dtype=torch.float32)

        H = self.G.clone()
        H.x = torch.tensor(self.scalers['weight'].transform(weight.view(-1, 1)), dtype=torch.float32)
        H.y = torch.tensor(self.scalers['regret'].transform(regret.view(-1, 1)), dtype=torch.float32)

        return H
