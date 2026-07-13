"""
Arquitetura do modelo GNN — cópia de "GNN Model/gnn_model.py" (adaptada de
https://github.com/walidgeuttala/atsp, src/model.py).

O modelo prediz, para cada arco do grafo ATSP (nó do line graph direcionado),
o "regret": quanto o custo do tour ótimo piora se aquele arco for forçado na
solução. No line graph DIRECIONADO, as convoluções direcionais ("dir-gat",
"dir-sage") ganham semântica real: o fluxo source->target agrega os arcos que
CONTINUAM o caminho e o fluxo target->source agrega os que o PRECEDEM.

Adaptação herdada: removida a dependência de `torch_sparse` (sem wheel para
torch 2.9 + Windows). Isso descarta apenas o conv "dir-gcn"; o padrão de
treino ("dir-gat") é mantido intacto.
"""

import torch
from torch import nn
import torch.nn.functional as F
from torch.nn import ModuleList, Linear
from torch_geometric.nn import (
    SAGEConv,
    GCNConv,
    GATConv,
    GENConv,
    DirGNNConv,
    JumpingKnowledge,
)


def get_conv(conv_type, input_dim, output_dim, alpha):
    if conv_type == "gcn":
        return GCNConv(input_dim, output_dim, add_self_loops=False)
    elif conv_type == "sage":
        return SAGEConv(input_dim, output_dim)
    elif conv_type == "gat":
        return GATConv(input_dim, output_dim, heads=1)
    elif conv_type == "gen":
        return GENConv(input_dim, output_dim, aggr='powermean', t=1.0,
                       learn_t=True, num_layers=2, norm='layer')
    elif conv_type == "dir-sage":
        return DirSageConv(input_dim, output_dim, alpha)
    elif conv_type == "dir-gat":
        return DirGATConv(input_dim, output_dim, heads=1, alpha=alpha)
    elif conv_type == 'dir-gen':
        return DirGNNConv(GENConv(input_dim, output_dim, aggr='powermean', t=1.0,
                                  learn_t=True, num_layers=2, norm='layer'))
    else:
        raise ValueError(f"Convolution type {conv_type} not supported")


class DirSageConv(torch.nn.Module):
    def __init__(self, input_dim, output_dim, alpha):
        super(DirSageConv, self).__init__()

        self.input_dim = input_dim
        self.output_dim = output_dim

        self.conv_src_to_dst = SAGEConv(input_dim, output_dim, flow="source_to_target", root_weight=False)
        self.conv_dst_to_src = SAGEConv(input_dim, output_dim, flow="target_to_source", root_weight=False)
        self.lin_self = Linear(input_dim, output_dim)
        self.alpha = alpha

    def forward(self, x, edge_index):
        return (
            self.lin_self(x)
            + (1 - self.alpha) * self.conv_src_to_dst(x, edge_index)
            + self.alpha * self.conv_dst_to_src(x, edge_index)
        )


class DirGATConv(torch.nn.Module):
    def __init__(self, input_dim, output_dim, heads, alpha):
        super(DirGATConv, self).__init__()

        self.input_dim = input_dim
        self.output_dim = output_dim

        self.conv_src_to_dst = GATConv(input_dim, output_dim, heads=heads)
        self.conv_dst_to_src = GATConv(input_dim, output_dim, heads=heads)
        self.alpha = alpha

    def forward(self, x, edge_index):
        edge_index_t = torch.stack([edge_index[1], edge_index[0]], dim=0)

        return (1 - self.alpha) * self.conv_src_to_dst(x, edge_index) + self.alpha * self.conv_dst_to_src(
            x, edge_index_t
        )


class GNN(torch.nn.Module):
    def __init__(
        self,
        num_features,
        num_classes,
        hidden_dim,
        num_layers=2,
        dropout=0,
        conv_type="dir-gat",
        jumping_knowledge=False,
        normalize=False,
        alpha=1 / 2,
        learn_alpha=False,
    ):
        super(GNN, self).__init__()

        self.alpha = nn.Parameter(torch.ones(1) * alpha, requires_grad=learn_alpha)
        output_dim = hidden_dim if jumping_knowledge else num_classes

        if num_layers == 1:
            self.convs = ModuleList([get_conv(conv_type, num_features, output_dim, self.alpha)])
        else:
            self.convs = ModuleList([get_conv(conv_type, num_features, hidden_dim, self.alpha)])
            for _ in range(num_layers - 2):
                self.convs.append(get_conv(conv_type, hidden_dim, hidden_dim, self.alpha))
            self.convs.append(get_conv(conv_type, hidden_dim, output_dim, self.alpha))

        if jumping_knowledge != False:
            input_dim = hidden_dim * num_layers if jumping_knowledge == "cat" else hidden_dim
            self.lin = Linear(input_dim, num_classes)

            self.jump = JumpingKnowledge(mode=jumping_knowledge, channels=hidden_dim, num_layers=num_layers)
        else:
            self.lin = Linear(output_dim, num_classes)
        self.num_layers = num_layers
        self.dropout = dropout
        self.jumping_knowledge = jumping_knowledge
        self.normalize = normalize

    def forward(self, x, edge_index):
        xs = []
        for i, conv in enumerate(self.convs):
            x = conv(x, edge_index)
            if i != len(self.convs) - 1 or self.jumping_knowledge:
                x = F.selu(x)
                x = F.dropout(x, p=self.dropout, training=self.training)
                if self.normalize:
                    x = F.normalize(x, p=2, dim=1)
            xs += [x]

        if self.jumping_knowledge != False:
            x = self.jump(xs)
            x = self.lin(x)

        return x


def build_model(params):
    """Instancia o GNN a partir de um dict de hiperparâmetros (params.json)."""
    return GNN(
        num_features=params.get("num_features", 1),
        num_classes=params.get("num_classes", 1),
        hidden_dim=params["hidden_dim"],
        num_layers=params["num_layers"],
        dropout=params.get("dropout", 0.0),
        conv_type=params.get("conv_type", "dir-gat"),
        jumping_knowledge=params.get("jk", False),
        normalize=params.get("normalize", False),
        alpha=params.get("alpha", 0.5),
        learn_alpha=params.get("learn_alpha", False),
    )
