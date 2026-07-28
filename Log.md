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

2.2 Claude Fable 5 (xHigh)

Claude, Vou refazer a estrutura do algoritmo de GNN, quero que você reutilize a atual estrutura e faça novos arquivos em uma pasta ATSP GNN Model, ajustando os dados e modelo para tratar de grafo unidirecionais, assim, treinando o modelo para instâncias a partir de matrizes assimétricas. Além disso, quero que você, dentro de uma nova pasta chamada "New ATSP Algo Comparison" copie a estrutura de New TSPs e crie um novo script de comparação dos mesmos algoritmos, porém, dessa vez, comparado durantes instâncias assimétrica.

3.0 Claude Fable 5 (xHigh)

Claude, agora eu preciso fazer o aplicativo em si. O intuito do aplicativo é realizar o processamento e cálculo de rotas para o roteamento de veículos. Ele deve receber uma imagem, na qual será realizado um OCR através da biblioteca PyTesseract. Os endereços que forem retirados dessa imagem, que provavelmente será uma nota fiscal ou então um pedido de compra, será limpado pelo sistema e, a partir disso, o formará uma lista com todos os endereços que o usuário selecionou das imagens, para que nós tenhamos a lista de endereços a qual será visitada. Além disso, o usuário também terá que colocar um ponto de início, que será o ponto zero, que é de onde o carro irá começar. Eu preciso que essa lista de endereços seja geocodificada através da API do OpenRouteService, na qual vou mandar a API depois, mas deve ser distribuído sem ela, para que o usuário possa colocar a própria API. A partir dessa matriz de distância que vai ser gerada através dessa lista que foi enviada para o sistema do OpenRouteServices, o sistema tem que realizar a otimização da rota, lembrando que essa rota muito provavelmente será devolvida em uma matriz assimétrica, então é muito importante que a gente deixe o algoritmo para funcionar em matrizes assimétricas.

O algoritmo escolhido será o Lin-Kernighan, que está já compilado na pasta de comparação. Para isso, eu preciso que você coloque ou uma cópia na pasta de app, ou então lembre-se de passar para a pasta do aplicativo em si. É muito importante a gente entender que essa aplicação, ela deve ser em Python, ela vai ser realizada em Python, só que eu quero que o front-end seja feito em React mais, ou então no que precisar, TypeScript, na qual eles vão se comunicar com uma forma de API, como a FastAPI, com o backend. Além disso, é muito importante a gente notar que eu preciso que esse sistema ele rode como um arquivo executável depois para ser distribuído. Então, eu não quero que ele abra no navegador. Eu quero que ele seja uma janela nativa que roda dentro do computador como se fosse feito por Tauri, na qual a parte esquerda terá como se fosse as configurações e a lista de rota que será calculada, e o botão de calcular rota, além do botão de colocar imagens e além da caixa de escrever o endereço, na qual deve ser pesquisada também pelo sistema do OpenRouteServices. Na parte central, deve ter um mapa, no qual assim que o usuário coloca o endereço, aparece um pin no mapa desse local onde o usuário pode mexer e alterar o endereço considerando a latitude e longitude do pin, o usuário pode também selecionar o ponto de parada direto no mapa. E na parte direita, é muito importante que a gente tenha uma lista já com a ordem final dos endereços (com tempo estimado de chegada a cada parada, dando a opção do usuário colocar hora de saída e tempo médio parado em cada ponto) a ser visitados e um botão na qual é realizada uma transferência dessa rota para o Google Maps. Então, para que o usuário possa apertar e abrir uma janela no Google, no navegador, com o Google Maps já com a rota pronta, saindo e voltando no ponto de origem.

(
""Plan Mode""

 ● Como empacotar o app como janela nativa executável? Você mencionou "como se fosse Tauri", mas o backend é Python — há formas diferentes de alcançar isso.
   → pywebview + PyInstaller
 ● O PyTesseract precisa do motor Tesseract OCR instalado na máquina. Como lidar com isso na distribuição do executável?
   → Embutir Tesseract portátil
 ● A otimização da rota (matriz do OpenRouteService) deve minimizar o quê?
   → O usuário deve escolher o que será otimizada (que sera o que vier na matriz distancia: Tempo ou Distância)
 ● Como o sistema deve "limpar" os endereços extraídos do OCR antes de o usuário selecioná-los?
   → Heurísticas + revisão do usuário (Recomendado)
)

###

Preciso que nas configurações fique salvo no computador do usuário, quando ele colocar a chave API pela primeira vez do OpenRouteServices. Assim, ele só precisa colocar a primeira vez que ele for utilizar e fica salvo. Além disso, eu quero que você retire das configurações a questão do OCR. Tem que ser tirado, já que ele é baixado junto com o arquivo. Então, não tem como o usuário colocar um caminho para o Tesseract.exe, até porque ele já vem baixado. Terceiro, eu quero que o zoom inicial do aplicativo comece em piracicaba - SP, na ESALQ. Além disso, o que eu preciso é que eu possa apertar com o botão direito no mapa e ter a opção adicionar parada, ou então adicionar início. Além disso, eu quero que a ferramenta de busca se torne um pouquinho melhor, para que eu possa escrever, por exemplo, R. e o nome da rua, que ele já buscar, ou então só o nome da rua que ele já buscar.

Além disso, eu preciso também que você reestruture a questão visual. A parte visual do programa não está legal. Será legal a gente demarcar as três sessões da página principal. Então, a sessão de configurações, a parte esquerda, no caso do meu, a parte central do mapa deixa como está e a parte da direita também. Eu queria que você utilizasse a cor #A51C30 para o visual base.

###

Preciso que você retire, da caixa de endereços, o botão "partida no mapa". Além disso, em configurações, a gente consegue selecionar tempo de viagem ou então distância. Eu quero que ao invés de ser uma caixa de selecionar, sejam dois botões, em que a gente consiga ver qual tá selecionado. Além disso, junto do adicionar imagens, vamos mudar para, adicionar imagens ou arquivos. Porque eu também quero que o programa consiga ler se o usuário mandar um arquivo em Excel, ou então CSV, com vários endereços. Então adicione essa funcionalidade de ler csv/.xlsx

###
Apenas por curiosidade, até aqui o trecho 3.0 gastou algo próximo de U$ 31,00
###

3.1 Claude Opus 5 (xHigh)

Coloque a logo que está na pasta de APP no .exe do aplicativo

3.2 Claude Opus 5

Claude, amplie a função de carregar imagens para aceitar PDFs também, além disso, quando for escolhido uma planilha, seja em csv ou em xlsx, abra uma janela na qual o usuário pode selecionar a coluna/células que estão os endereços