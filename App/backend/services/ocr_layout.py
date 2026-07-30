"""Reconstrói linhas de texto a partir de palavras posicionadas.

Agnóstico ao motor: entra `list[Word]`, sai `list[str]`. O Tesseract já numera linhas,
mas com `--psm 11` (texto esparso) ele devolve tudo como blocos soltos, e é justamente
esse modo que lê romaneio e nota fiscal. Manter a montagem aqui deixa a troca do motor
restrita a quem produz `Word`.
"""

from dataclasses import dataclass
from statistics import median

TOLERANCIA_LINHA = 0.6
# Abaixo disto o espaço é entre palavras; acima é o vão entre duas colunas do
# documento, e juntar os dois lados cola "Rua Alfredo Guedes 1949" com "NF 12345".
GAP_COLUNA = 2.5


@dataclass(frozen=True)
class Word:
    text: str
    conf: float
    left: int
    top: int
    width: int
    height: int

    @property
    def centro_y(self) -> float:
        return self.top + self.height / 2

    @property
    def right(self) -> int:
        return self.left + self.width


def _agrupar_linhas(palavras: list[Word], tolerancia: float) -> list[list[Word]]:
    linhas: list[list[Word]] = []
    for w in sorted(palavras, key=lambda p: p.centro_y):
        if linhas and abs(w.centro_y - linhas[-1][-1].centro_y) <= tolerancia:
            linhas[-1].append(w)
        else:
            linhas.append([w])
    return [sorted(linha, key=lambda p: p.left) for linha in linhas]


def _largura_caractere(palavras: list[Word]) -> float:
    larguras = [w.width / len(w.text) for w in palavras if w.text]
    return median(larguras) if larguras else 1.0


def _quebrar_colunas(linha: list[Word], largura_char: float) -> list[list[Word]]:
    limite = largura_char * GAP_COLUNA
    blocos = [[linha[0]]]
    for anterior, atual in zip(linha, linha[1:]):
        if atual.left - anterior.right > limite:
            blocos.append([atual])
        else:
            blocos[-1].append(atual)
    return blocos


def _colunas(blocos: list[list[Word]]) -> list[list[list[Word]]]:
    """Merge de intervalos horizontais: blocos que se sobrepõem em x são a mesma coluna.

    Emitir na ordem de leitura visual intercalaria o endereço com a coluna de notas ao
    lado, e o parser lê o endereço numa janela de linhas vizinhas — o logradouro ficaria
    longe do CEP. Um cabeçalho que atravesse a página funde tudo numa coluna só, o que
    apenas devolve o comportamento intercalado."""
    grupos: list[list[list[Word]]] = []
    alcance = -1
    for bloco in sorted(blocos, key=lambda b: min(w.left for w in b)):
        inicio = min(w.left for w in bloco)
        if grupos and inicio <= alcance:
            grupos[-1].append(bloco)
        else:
            grupos.append([bloco])
            alcance = -1
        alcance = max(alcance, max(w.right for w in bloco))
    return grupos


def montar_linhas(palavras: list[Word]) -> list[str]:
    uteis = [w for w in palavras if w.text.strip()]
    if not uteis:
        return []
    tolerancia = median([w.height for w in uteis]) * TOLERANCIA_LINHA
    largura_char = _largura_caractere(uteis)

    blocos: list[list[Word]] = []
    for linha in _agrupar_linhas(uteis, tolerancia):
        blocos.extend(_quebrar_colunas(linha, largura_char))

    linhas: list[str] = []
    for coluna in _colunas(blocos):
        for bloco in sorted(coluna, key=lambda b: min(w.centro_y for w in b)):
            texto = " ".join(w.text for w in bloco).strip()
            if texto:
                linhas.append(texto)
    return linhas


def confianca_media(palavras: list[Word]) -> float:
    uteis = [w for w in palavras if w.text.strip()]
    return sum(w.conf for w in uteis) / len(uteis) if uteis else 0.0
