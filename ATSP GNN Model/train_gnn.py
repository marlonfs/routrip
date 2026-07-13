"""
Treino do GNN de predição de regret para o ATSP — adaptado de
"GNN Model/train_gnn.py" (originalmente de https://github.com/walidgeuttala/atsp).

Treina UM checkpoint por tamanho de instância (o dataset/line graph é
homogêneo por tamanho) e salva em:
    checkpoints/atsp{n}/checkpoint_best_val.pt   (melhor val loss)
    checkpoints/atsp{n}/params.json              (hiperparâmetros do modelo)
    checkpoints/atsp{n}/scalers.pkl              (cópia dos scalers do dataset)

Diferenças em relação à versão TSP:
    * Dataset direcionado (ATSPDataset) em data/atsp{n};
    * O line graph direcionado tem n(n-1) nós (o dobro da versão simétrica),
      então os batches dos tamanhos grandes são menores.

Uso:
    python train_gnn.py                  # treina todos os tamanhos com dados em ./data
    python train_gnn.py --sizes 50 100   # apenas alguns tamanhos
"""

import argparse
import json
import os
import pickle
import shutil
import time

import numpy as np
import torch
from torch_geometric.loader import DataLoader

from gnn_model import build_model
from gnn_dataset import ATSPDataset
from gnn_algorithms import nearest_neighbor, tour_cost

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Batch (nº de grafos por batch) por tamanho — o line graph direcionado tem
# n(n-1) nós e ~n(n-1)² arcos, o dobro da versão simétrica, então os tamanhos
# grandes usam batches menores para caber em CPU/RAM.
BATCH_SIZES = {5: 8, 10: 8, 20: 8, 50: 2, 100: 1}

# Épocas por tamanho: os pequenos são baratos (segundos/época) e precisam de
# mais épocas para acumular passos de gradiente.
EPOCHS = {5: 300, 10: 300, 20: 200, 50: 100, 100: 60}


def train_epoch(model, loader, criterion, optimizer, device):
    model.train()
    epoch_loss = 0.0
    for batch_i, batch in enumerate(loader):
        batch = batch.to(device)
        optimizer.zero_grad()
        y_pred = model(batch.x, batch.edge_index)
        loss = criterion(y_pred.squeeze(), batch.y.type_as(y_pred).squeeze())
        loss.backward()
        optimizer.step()
        epoch_loss += loss.detach().item()
    return epoch_loss / (batch_i + 1)


@torch.no_grad()
def eval_epoch(model, loader, criterion, device):
    model.eval()
    epoch_loss = 0.0
    for batch_i, batch in enumerate(loader):
        batch = batch.to(device)
        y_pred = model(batch.x, batch.edge_index)
        loss = criterion(y_pred.squeeze(), batch.y.type_as(y_pred).squeeze())
        epoch_loss += loss.item()
    return epoch_loss / (batch_i + 1)


@torch.no_grad()
def val_gap(model, val_data, device):
    """Gap (%) do tour NN guiado por regret_pred vs custo ótimo, na validação."""
    model.eval()
    gaps = []
    for instance in val_data.instances:
        with open(val_data.root_dir / instance, 'rb') as f:
            G = pickle.load(f)
        H = val_data.get_scaled_features(G).to(device)
        y_pred = model(H.x, H.edge_index)
        regret_pred = val_data.scalers['regret'].inverse_transform(y_pred.cpu().numpy())
        for idx in range(H.num_nodes):
            u, v = val_data.mapping[idx]
            G[u][v]['regret_pred'] = max(regret_pred[idx].item(), 0.0)

        opt_cost = sum(G.edges[e]['weight'] for e in G.edges if G.edges[e]['in_solution'])
        init_tour = nearest_neighbor(G, 0, weight='regret_pred')
        init_cost = tour_cost(G, init_tour, weight='weight')
        gaps.append((init_cost / opt_cost - 1) * 100)
    return float(np.mean(gaps))


def train_size(n, args):
    data_dir = os.path.join(args.data_dir, f"atsp{n}")
    ckpt_dir = os.path.join(args.checkpoint_dir, f"atsp{n}")
    os.makedirs(ckpt_dir, exist_ok=True)

    train_data = ATSPDataset(os.path.join(data_dir, "train.txt"))
    val_data = ATSPDataset(os.path.join(data_dir, "val.txt"))

    batch_size = args.batch_size or BATCH_SIZES.get(n, 8)
    n_epochs = args.n_epochs or EPOCHS.get(n, 100)
    train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_data, batch_size=batch_size, shuffle=False, num_workers=0)

    device = torch.device(args.device)
    torch.manual_seed(0)

    params = {
        "num_features": 1,
        "num_classes": 1,
        "hidden_dim": args.hidden_dim,
        "num_layers": args.num_layers,
        "dropout": args.dropout,
        "conv_type": args.conv_type,
        "jk": args.jk,
        "normalize": False,
        "alpha": 0.5,
        "learn_alpha": False,
        "target": "regret",
        "instance_size": n,
    }
    model = build_model(params).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr_init)
    lr_scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizer, args.lr_decay)
    criterion = torch.nn.MSELoss()

    best_score = None
    counter = 0
    best_path = os.path.join(ckpt_dir, "checkpoint_best_val.pt")

    print(f"\n===== Treinando atsp{n} "
          f"({len(train_data)} treino / {len(val_data)} val, batch {batch_size}) =====", flush=True)

    for epoch in range(n_epochs):
        t0 = time.perf_counter()
        train_loss = train_epoch(model, train_loader, criterion, optimizer, device)
        val_loss = eval_epoch(model, val_loader, criterion, device)
        dt = time.perf_counter() - t0
        print(f"[atsp{n}] época {epoch + 1:3d}/{n_epochs} | "
              f"train {train_loss:.5f} | val {val_loss:.5f} | {dt:.1f}s", flush=True)

        if best_score is None or val_loss < best_score - args.min_delta:
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'loss': train_loss,
                'val_loss': val_loss,
            }, best_path)
            best_score = val_loss
            counter = 0
        else:
            counter += 1

        if counter >= args.patience:
            print(f"[atsp{n}] early stopping (paciência {args.patience})", flush=True)
            break

        lr_scheduler.step()

    json.dump(params, open(os.path.join(ckpt_dir, "params.json"), "w"), indent=2)
    shutil.copyfile(os.path.join(data_dir, "scalers.pkl"),
                    os.path.join(ckpt_dir, "scalers.pkl"))

    # Avaliação final com o melhor checkpoint
    checkpoint = torch.load(best_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint['model_state_dict'])
    gap = val_gap(model, val_data, device)
    print(f"[atsp{n}] melhor val loss {best_score:.5f} (época {checkpoint['epoch'] + 1}) | "
          f"gap NN(regret_pred) na validação: {gap:.2f}%", flush=True)


def parse_args():
    parser = argparse.ArgumentParser("Treino do GNN ATSP (regret) por tamanho de instância")
    parser.add_argument("--sizes", type=int, nargs="+", default=[5, 10, 20, 50, 100])
    parser.add_argument("--data-dir", type=str, default=os.path.join(SCRIPT_DIR, "data"))
    parser.add_argument("--checkpoint-dir", type=str, default=os.path.join(SCRIPT_DIR, "checkpoints"))

    # Modelo (mesmos nomes do repositório original)
    parser.add_argument("--hidden_dim", type=int, default=64)
    parser.add_argument("--num_layers", type=int, default=3)
    parser.add_argument("--dropout", type=float, default=0.0)
    parser.add_argument("--conv_type", type=str, default="dir-gat")
    parser.add_argument("--jk", type=str, choices=["max", "cat", "false"], default="cat")

    # Treino
    parser.add_argument("--lr_init", type=float, default=1e-3)
    parser.add_argument("--lr_decay", type=float, default=0.995,
                        help="Gamma do ExponentialLR (no original: --weight_decay).")
    parser.add_argument("--n_epochs", type=int, default=None,
                        help="Sobrescreve as épocas por tamanho (EPOCHS).")
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--min_delta", type=float, default=0.0)
    parser.add_argument("--batch_size", type=int, default=None,
                        help="Sobrescreve o batch por tamanho (BATCH_SIZES).")
    parser.add_argument("--device", type=str, default="cpu")

    args = parser.parse_args()
    if args.jk == "false":
        args.jk = False
    return args


if __name__ == "__main__":
    args = parse_args()
    for n in args.sizes:
        train_size(n, args)
