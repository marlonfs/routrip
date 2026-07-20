<div align="center">

# 🚚 RouTrip

### An Integrated Approach to the Asymmetric Traveling Salesman Problem

[![Paper](https://img.shields.io/badge/Read-the_paper-2ea44f.svg)](#)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE.md)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Contributions welcome](https://img.shields.io/badge/Contributions-welcome-orange.svg)](CONTRIBUTING.md)
[![Release](https://img.shields.io/github/release/marlonfs/routrip.svg?label=Release)](https://github.com/marlonfs/routrip/releases)

</div>

---

## Overview

**RouTrip** applies heuristic and machine-learning algorithms to the **Asymmetric
Traveling Salesman Problem (ATSP)** for multi-stop addresses, with the goal of
building a functional application for **last-mile deliveries**.

The proposed application integrates:

- **Tesseract** — address extraction (OCR) from order sheets;
- **GenAI models** — address interpretation and correction;
- **OpenRouteService API** — generation of an asymmetric *from-to* distance matrix.

The **Jonker & Volgenant** method converts the asymmetric matrix into a symmetric
one, enabling **five algorithms** to be tested and compared.

## Highlights

- **GenAI-supported coding** — We evaluate whether current generative artificial
  intelligence (GenAI) tools can effectively support non-senior programmers in
  building accurate and efficient systems.
- **Python backend.**
- **Frontend in React and TypeScript.**
- **Open-source routing application** — If successful, the system could provide a
  low-cost or cost-free alternative to existing solutions, benefiting small
  businesses and independent workers.

## Processing pipeline

```text
Order sheet  ──▶  Tesseract (OCR)  ──▶  GenAI (address interpretation & correction)
                                              │
                                              ▼
                            OpenRouteService (asymmetric distance matrix)
                                              │
                                              ▼
                        Jonker & Volgenant (asymmetric ──▶ symmetric)
                                              │
                                              ▼
                     Five algorithms tested & compared  ──▶  Optimized route
```

## Repository structure

```text
routrip/
├── Comparison/
│   ├── Algo comparison/        # Symmetric TSP benchmark (LKH3, OR-Tools, NN, ACO, Simplex)
│   ├── New-Algo Comparison/    # Metaheuristic & learning benchmark (LKH3, ILS, ALNS, HGS, GNN)
│   ├── GNN Model/              # Graph Neural Network solver and training pipeline
│   └── requirements.txt
├── CONTRIBUTING.md
├── LICENSE.md
└── README.md
```

Each benchmark folder ships its own README with the detailed methodology:
[`Comparison/New-Algo Comparison/README.md`](Comparison/New-Algo%20Comparison/README.md)
and [`Comparison/GNN Model/README.md`](Comparison/GNN%20Model/README.md).

## Requirements

- **Python 3.11+**
- Dependencies listed in [`Comparison/requirements.txt`](Comparison/requirements.txt)

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/marlonfs/routrip
cd routrip

# 2. Install the required dependencies
pip install -r Comparison/requirements.txt

# 3. Download the provided sample dataset
```

## Usage

Run one of the comparison scripts to execute the benchmark and export the results:

```bash
# Symmetric TSP benchmark
python "Comparison/Algo comparison/TSPs.py"

# Metaheuristic & learning benchmark
python "Comparison/New-Algo Comparison/NewTSPs.py"
```

Each run produces an `.xlsx` spreadsheet with the total cost and computation time
per algorithm, instance, and seed.

## Contributing

We welcome contributions from the community. Please read the
[Contributing Guidelines](CONTRIBUTING.md) before opening an issue or a pull
request.

## License

This project is licensed under the [Apache License 2.0](LICENSE.md).
