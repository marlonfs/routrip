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

1.4 Claude Opus 4.7 (Max effort)

Estou fazendo um programa que roda diversas instâncias de TSP, preciso que você compile todos os arquivos de TSP em um só, ele deve realizar o TSP5, TSP10 e TSP20 com 20 seeds e o TSP50 e TSP100 com 5 seeds. O programa deve devolver o arquivo .xlsx chamado "Comparação TSPs", da mesma forma que já é feito nos outros arquivos, porem adicione a qual instância tal linha pertence, isso é, se o custo é do TSP5, 10, 20, 50 ou 100.


2.0 Claude Opus 4.8 (xHigh effort)

Estou fazendo um teste comparativo entre diversos algoritmos de otimização de planejamento de transporte.

Preciso que, para o teste, você faça uma matriz simétrica, representando uma matriz distância que será utilizada na otimização dos algoritmos, a matriz utilizada pelos algoritmos deve ser exatamente a mesma.

Os algoritmos que serão testaos serão:
LKH3, já instalado e disponível no repositório em Algo Comparison e será o método utilizado como Baseline a ser comparado com os outros métodos.;
Iterated Local Search, disponível na biblioteca registrada no Repositório: https://github.com/PyVRP/PyVRP/blob/main/pyvrp/IteratedLocalSearch.py
ALNS, Adaptative Large Neighbourhood Search, descrito no repositório: https://github.com/N-Wouda/ALNS/tree/master
e Hybrid Genetic Search, também descrita em https://github.com/chkwon/PyHygese.

O problema abordado é o Traveling Salesman Problem (TSP) por isso, o intuito dos algoritmos é saindo do ponto 1, visitar todas as outras paradas uma única vez e, ao final, voltar ao início reduzindo ao mínimo possível o custo total de viagem.

Os testes deverão ser realizados com 20 seeds diferentes, isso é, assim que todos os algoritmos resolverem o problem com a matriz custo de seed 1, o programa roda novamente com a seed 2.

Você deve considerar apenas instâncias de 5, 10, 20, 50 e 100 paradas, cada uma com 20 seeds.

Para comparação, preciso coletar os dados em uma planilha .xlxs onde posso ter os dados de tempo rodado por algoritmo, por instância e por seed. Além disso, em uma outra tabela, preciso ter o custo total encontrado por cada algoritmo, para cada instância e para cada seed.

Se atente ao fato de que as bibliotecas PyVRP e PyHygese não rodam o problema TSP, mas sim o VRP, então, por isso, você deve adaptar o código para rodar o TSP.

Crie esse arquivo em uma nova pasta chamada "New-Algo Comparison"
Lembre-se de utilizar o LKH já presente no repositório, não precisa utilizar nenhuma nova biblioteca, poder ser o compile lkh ou o lkh.exe, será rodado em Windows

2.1 Claude Fable 5 (xHigh effort)

Claude, preciso adicionar a comparação mais recente - New-Algo Comparison um modelo de resolução feito por GNN, o modelo base que quero que você utilize é o disponível em https://github.com/walidgeuttala/atsp.git. Para colocá-lo, será necessário treinar o modelo, por isso, durante a implementação do modelo, quando você precisar realizar esse treino, coloque os arquivos em uma pasta separada com o nome de "GNN Model"