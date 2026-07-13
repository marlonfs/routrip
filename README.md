[![Read the project](https://img.shields.io/badge/Read-the_paper-green.svg)](https://)
[![Contribute](https://img.shields.io/static/v1?label=Contribute&message=💪)](#contribute)
![Release](https://img.shields.io/github/release/Center-for-Plasticulture-Engineering/RSdetection_PMF.svg?label=Release)


<h1>RouTrip: An integrated approach to the Asymmetric Traveling Salesman Problem</h1>

## Introduction

Welcome to the **Routrip** project! This project uses heuristic and machine learning algorithms to solve the asymmetric traveling salesman problem (ATSP) for multi-stop addresses, aiming at the development of a functional application for use in last-mile deliveries. The proposed app integrates Tesseract for address extraction from order sheets, GenAI models for address interpretation and correction, and the OpenRouteService API for generating an asymmetric from-to distance matrix. The Jonker & Volgenant method is applied to convert the asymmetric matrix into a symmetric one, enabling five algorithms to be tested and compared.

## Highlights

- **GenAI supported coding**: We are evaluating whether current generative artificial intelligence (GenAI) tools can effectively support non-senior programmers in building accurate and efficient systems.
- **Python backend**
- **frontend in React and TypeScript**
- **Open-source routing application**: If successful, the system could provide a low-cost or cost-free alternative to existing systems, benefiting small businesses and independent workers.


## Installation

To get started with the project, follow these steps:

1. Clone the repository: `git clone https://github.com/marlonfs/routrip`
2. Install the required dependencies: `pip install -r requirements.txt`
3. Download the sample dataset provided. 
4. Run the script in the file `TSPs.py` or `NewTSPs.py` to run and download the final results.
   
  
## Contributing

We welcome contributions from the community to enhance the project. If you would like to contribute, please follow the guidelines outlined in [CONTRIBUTING](CONTRIBUTING.md).

## License

This project is licensed under the [Apache License 2.0](LICENSE.md)
