1.1 - Gemini 3.5 Flash (High)

Estou fazendo um teste comparativo entre diversos algoritmos de otimização de planejamento de transporte.

Preciso que, para o teste, você faça uma matriz simétrica, representando uma matriz distância que será utilizada na otimização dos algoritmos, a matriz utilizada pelos algoritmos deve ser exatamente a mesma.

Os algoritmos que serão testaos serão:
LKH3, descrito no artigo "An Extension of the Lin-Kernighan-Helsgaun TSP Solver for
Constrained Traveling Salesman and
Vehicle Routing Problems";
Google OR-Tools, documentado no link https://developers.google.com/optimization/routing/tsp?hl=pt-br;
Algoritmo de vizinho mais próximo (Nearest-Neighbor);
e Ant Colony Optimization, descrito no artigo "Ant colony system: A cooperative learning
approach to the traveling salesman problem.".

Como método de base, implemente o resolvedor "Simplex" para alcançar um resultado ótimo.

O problema abordado é o Traveling Salesman Problem (TSP) por isso, o intuito dos algoritmos é saindo do ponto 1, visitar todas as outras paradas uma única vez e, ao final, voltar ao início reduzindo ao mínimo possível o custo total de viagem.

Os testes deverão ser realizados com 20 seeds diferentes, isso é, assim que todos os algoritmos resolverem o problem com a matriz custo de seed 1, o programa roda novamente com a seed 2.

Para comparação, preciso coletar os dados em uma planilha .xlxs onde:
Na primeira folha da planilha esteja contida o tempo de cálculo utilizado por cada algoritmo e custo total achado por cada algoritmo em cada seed.

"""

O numero de paradas no TSP5 é de 5 paradas

"""

Altere para que o excel seja instalado diretamente no computador do usuário, sem ficar no repositório. O nome do arquivo deve ser: "Comparação TSP5"

1.2 Claude Opus 4.7 (Max effort)

Ative nos arquivos TSP5, TSP10 e TSP20 no algoritmo "Google-OR Tools" a opção de uma metaheurística de melhoria no resultado. Permitindo que a primeira solução seja exposta a um processo de melhoria. Não restrinja um tempo_limite.

"""
[Quer que eu adicione um solution_limit para garantir a terminação sem impor restrição de tempo?
 
 Sim, adicione]

1.3 Claude Opus 4.7 (Max effort)

Reescreva em Colab.py todo o código necessário para eu rodar o TSP50 no Google Colab, isso é, inclua os "pip install" necessários, download do LKH e qualquer outro quesito necessário sem alterar a lógica