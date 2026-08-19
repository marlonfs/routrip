"""Consulta à base local do CNEFE/IBGE.

Duas perguntas: "onde fica este CEP?" e "esta rua existe neste município?". A segunda
é a que permite só oferecer ao usuário endereços que existem de verdade.

A base é opcional. Sem ela o app continua funcionando — a validação de endereço
apenas perde a âncora geográfica e passa a depender só do ViaCEP.
"""

import math
import sqlite3
import threading
from bisect import bisect_left
from difflib import SequenceMatcher
from typing import Any, NamedTuple

from core.paths import cnefe_db
from core.schemas import (CnefeCep, CnefeLogradouro, CnefeMunicipio, CnefeStatus,
                          NumeroStatus)
from services import br_address_terms as termos

_local = threading.local()
# Só a conexão é por thread; o que ela devolve, não. As linhas do sqlite são tuplas
# com os nomes das colunas ao lado, sem referência à conexão que as trouxe, então
# valem para qualquer thread. Deixá-las no `_local` multiplicava os índices pelas 40
# threads do threadpool do FastAPI — 63 MB medidos por thread só com a Grande São Paulo.
# Duas threads podem montar o mesmo índice ao mesmo tempo: o desperdício é o trabalho
# repetido, e a atribuição no dict é atômica sob o GIL.
_memo: dict[str, Any] = {}

_CAMPOS_CEP = ("cep", "lat", "lon", "raio_m", "generico", "n_enderecos",
               "logradouro", "localidade", "cod_ibge")

# Medido sobre as 300 ruas mais movimentadas de Piracicaba: de 0,60 a 0,80 o acerto com
# texto corrompido fica em 96%, mas só a partir de 0,70 nenhuma rua inventada recebe
# resposta. Abaixo disso "Rua Inventada Que Não Existe" casava com "Avenida Investigador
# Lucídio Leite" — exatamente o que não pode ser oferecido.
SIM_MIN = 0.7
SIM_MUNICIPIO_MIN = 0.85
# Teto do cache de índices em linhas, não em municípios: "três municípios" custa 4 MB
# no interior e 110 MB quando os três são São Paulo, Rio e Belo Horizonte, e é o
# segundo caso que decide se o app cabe na máquina do usuário.
LINHAS_EM_CACHE = 150_000
# Ruas cuja numeração fica decodificada. Uma busca toca no máximo `limite` delas.
NUMERACAO_EM_CACHE = 128
# Mesmo teto que o build aplica ao raio: quem chegou nele é via de dezenas de
# quilômetros, sem posição confiável para o número.
RAIO_TETO_M = 5000
# Token presente em boa parte das ruas do município ("dos", "santos") não separa nada
# e traz milhares de candidatos para o comparador caro.
FRACAO_TOKEN_INUTIL = 0.3
# Teto de linhas comparadas por busca. "Rua Sete De Setembro" unia o posting de "de"
# — mil ruas em Piracicaba — e a busca levava 20 ms em vez de 0,4 ms.
CANDIDATOS_MAX = 400
# Passo da quantização das coordenadas da numeração. Tem de ser igual ao QUANT_E6 de
# tools/build_cnefe.py: é o formato do blob, não uma preferência de leitura.
QUANT_E6 = 11
# Só para medir o antes/depois na mesma base, sem guardar o arquivo antigo de 263 MB.
FORCAR_V1 = False
# Fecha o range scan por prefixo na chave primária: nenhum nome normalizado chega aqui,
# porque a normalização só deixa passar letras, dígitos e espaço.
FIM_DO_PREFIXO = "￿"


def _conexao() -> sqlite3.Connection | None:
    """Uma conexão por thread: os endpoints `def` do FastAPI rodam no threadpool e
    conexão sqlite não pode cruzar threads."""
    con = getattr(_local, "con", None)
    if con is not None:
        return con
    caminho = cnefe_db()
    if caminho is None:
        return None
    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    _local.con = con
    return con


def disponivel() -> bool:
    return _conexao() is not None


def limpar_conexao() -> None:
    """Chamado após regravar o arquivo, para que a próxima consulta reabra a base.

    Os caches vão junto: fechar só a conexão deixava os índices, os tipos e a meta da
    base antiga vivos, e a busca continuaria respondendo pelo arquivo que já não existe.
    """
    con = getattr(_local, "con", None)
    if con is not None:
        con.close()
    _local.con = None
    _memo.clear()


def normalizar_cep(cep: str) -> str | None:
    digitos = "".join(c for c in cep if c.isdigit())
    return digitos if len(digitos) == 8 else None


def lookup(cep: str) -> CnefeCep | None:
    con = _conexao()
    limpo = normalizar_cep(cep)
    if con is None or limpo is None:
        return None
    row = con.execute(
        f"SELECT {','.join(_CAMPOS_CEP)} FROM cep WHERE cep = ?", (limpo,)
    ).fetchone()
    if row is None:
        return None
    return CnefeCep(
        cep=row["cep"],
        lat=row["lat"] / 1e6,
        lon=row["lon"] / 1e6,
        raio_m=row["raio_m"],
        generico=bool(row["generico"]),
        n_enderecos=row["n_enderecos"],
        logradouro=row["logradouro"],
        localidade=row["localidade"],
        cod_ibge=row["cod_ibge"],
        municipio=None if row["cod_ibge"] is None else lookup_municipio(row["cod_ibge"]),
    )


def lookup_municipio(cod_ibge: str) -> CnefeMunicipio | None:
    con = _conexao()
    if con is None:
        return None
    row = con.execute(
        "SELECT cod_ibge, nome, uf, lat, lon, raio_m, n_ceps FROM municipio WHERE cod_ibge = ?",
        (cod_ibge,),
    ).fetchone()
    if row is None:
        return None
    return CnefeMunicipio(
        cod_ibge=row["cod_ibge"],
        nome=row["nome"],
        uf=row["uf"],
        lat=row["lat"] / 1e6,
        lon=row["lon"] / 1e6,
        raio_m=row["raio_m"],
        n_ceps=row["n_ceps"],
    )


def _meta() -> dict[str, str]:
    """Em cache: `tem_numeracao()` é consultado uma vez por rua proposta, e sem cache
    cada busca viraria uma dúzia de SELECTs para ler a mesma linha."""
    pronto = _memo.get("meta")
    if pronto is not None:
        return pronto
    con = _conexao()
    try:
        pronto = {k: v for k, v in con.execute("SELECT chave, valor FROM meta")} if con else {}
    except sqlite3.OperationalError:
        pronto = {}
    _memo["meta"] = pronto
    return pronto


def _versao_indice() -> int:
    try:
        return int(_meta().get("versao_indice", "0"))
    except ValueError:
        return 0


def busca_por_rua() -> bool:
    """Uma base gerada antes do índice tem as tabelas de CEP idênticas e passaria
    despercebida; só a chave em `meta` distingue as duas."""
    return _versao_indice() >= 1


def tem_numeracao() -> bool:
    """A base guarda a coordenada de cada casa cadastrada (versão 2), e não só os dois
    extremos da rua. Sem isso a posição do número é interpolada e erra 105 m na mediana."""
    return not FORCAR_V1 and _versao_indice() >= 2


def status() -> CnefeStatus:
    con = _conexao()
    if con is None:
        return CnefeStatus(disponivel=False)
    meta = _meta()
    return CnefeStatus(
        disponivel=True,
        fonte=meta.get("fonte"),
        gerado_em=meta.get("gerado_em"),
        n_ceps=int(meta.get("n_ceps", 0)),
        n_municipios=int(meta.get("n_municipios", 0)),
        n_logradouros=int(meta.get("n_logradouros", 0)),
        n_numeros=int(meta.get("n_numeros", 0)),
        busca_por_rua=busca_por_rua(),
        numeracao=tem_numeracao(),
        caminho=str(cnefe_db()),
    )


def distancia_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 6_371_000 * 2 * math.asin(math.sqrt(a))


# --- busca por logradouro ----------------------------------------------------

_CAMPOS_LOG = ("nome", "tipo", "n_end", "cep", "lat", "lon", "raio_m",
               "num_min", "num_max", "dlat_min", "dlon_min", "dlat_max", "dlon_max")


def _campos_log() -> tuple[str, ...]:
    """`id` só existe na base v2; pedi-lo numa v1 mataria a busca com "no such column"."""
    return _CAMPOS_LOG + ("id",) if tem_numeracao() else _CAMPOS_LOG


def _tipos() -> dict[int, str]:
    tipos = _memo.get("tipos")
    if tipos is None:
        con = _conexao()
        tipos = ({i: nome for i, nome in con.execute("SELECT id, nome FROM tipo_logradouro")}
                 if con is not None else {})
        _memo["tipos"] = tipos
    return tipos


def _tipos_por_nome() -> tuple[dict[str, int], int]:
    """Vocabulário de tipos do próprio CNEFE — 390 deles, contra a dúzia que o parser de
    endereço reconhece. Sem consultá-lo, "Caminho 1" (979 casas em Salvador) não acha
    nada, porque na base essa linha ficou só como "1", com o tipo guardado à parte."""
    pronto = _memo.get("tipos_nome")
    if pronto is None:
        vocab = {termos.normalizar(nome): i for i, nome in _tipos().items() if nome}
        pronto = (vocab, max((len(n.split()) for n in vocab), default=1))
        _memo["tipos_nome"] = pronto
    return pronto


def _separar_tipo(bruto: str) -> tuple[str, str, str]:
    """(tipo, nome sem o tipo, texto inteiro normalizado).

    A base guarda o nome sem o tipo, senão "Rua" pesaria no comparador tanto quanto o
    nome próprio; o tipo volta só no desempate, para separar Avenida de Travessa
    Paulista, que fora dele são idênticas. O vocabulário da base tem prioridade sobre o
    regex do parser porque ele é que descreve como a linha foi gravada — inclusive
    tipos compostos como "1A Travessa da Rua". O regex fica para as abreviações
    ("R.", "Av."), que a base não conhece.
    """
    cheio = termos.normalizar(bruto)
    palavras = cheio.split()
    vocab, maior = _tipos_por_nome()
    for n in range(min(maior, len(palavras) - 1), 0, -1):
        if " ".join(palavras[:n]) in vocab:
            return " ".join(palavras[:n]), " ".join(palavras[n:]), cheio
    achado = termos.TIPO_LOGRADOURO.search(bruto)
    tipo = termos.normalizar(termos.expandir_tipo(achado.group(1)) or "") if achado else ""
    return tipo, termos.normalizar(termos.TIPO_LOGRADOURO.sub(" ", bruto)) or cheio, cheio


def _indice(cod_ibge: int) -> tuple[list[sqlite3.Row], dict[str, list[int]]] | None:
    """Carrega as ruas de um município e monta um índice invertido em RAM.

    Um índice textual no arquivo (FTS5) custaria dezenas de MB no disco para responder
    o que este dict responde em milissegundos: as paradas de uma rota estão quase
    sempre no mesmo município, então basta um punhado deles de cada vez.
    """
    cache: dict[int, tuple] = _memo.setdefault("indices", {})
    pronto = cache.get(cod_ibge)
    if pronto is not None:
        return pronto

    con = _conexao()
    if con is None:
        return None
    linhas = con.execute(
        f"SELECT {','.join(_campos_log())} FROM logradouro WHERE cod_ibge = ?", (cod_ibge,)
    ).fetchall()
    if not linhas:
        return None

    postings: dict[str, list[int]] = {}
    for i, row in enumerate(linhas):
        # O prefixo de quatro letras entra junto para tolerar o erro de OCR no fim da
        # palavra ("NABUC0" continua achando "nabuco").
        for token in set(row["nome"].split()):
            postings.setdefault(token, []).append(i)
            if len(token) > 4:
                postings.setdefault(token[:4], []).append(i)

    cache[cod_ibge] = (linhas, postings)
    # Sobre uma cópia: outra thread pode inserir no meio da varredura, e aí iterar o
    # próprio dict estoura. O recém-carregado nunca é despejado, mesmo sozinho maior
    # que o teto — era a razão de a busca ter sido feita.
    itens = list(cache.items())
    total = sum(len(v[0]) for _, v in itens)
    for chave, valor in itens:
        if total <= LINHAS_EM_CACHE or chave == cod_ibge:
            break
        if cache.pop(chave, None) is not None:
            total -= len(valor[0])
    return cache[cod_ibge]


def _municipios() -> dict[str, list[sqlite3.Row]]:
    """Os 5.570 municípios cabem folgados na memória e a busca por nome é frequente."""
    por_nome = _memo.get("municipios")
    if por_nome is not None:
        return por_nome
    con = _conexao()
    por_nome = {}
    if con is not None:
        for row in con.execute("SELECT cod_ibge, nome, uf, lat, lon, raio_m, n_ceps "
                               "FROM municipio WHERE nome IS NOT NULL"):
            por_nome.setdefault(termos.normalizar(row["nome"]), []).append(row)
    _memo["municipios"] = por_nome
    return por_nome


def _municipios_lista() -> list[sqlite3.Row]:
    """A mesma tabela, plana, para a varredura por proximidade."""
    pronto = _memo.get("municipios_lista")
    if pronto is None:
        pronto = [row for linhas in _municipios().values() for row in linhas]
        _memo["municipios_lista"] = pronto
    return pronto


def _para_municipio(row: sqlite3.Row) -> CnefeMunicipio:
    return CnefeMunicipio(cod_ibge=row["cod_ibge"], nome=row["nome"], uf=row["uf"],
                          lat=row["lat"] / 1e6, lon=row["lon"] / 1e6,
                          raio_m=row["raio_m"], n_ceps=row["n_ceps"])


def municipio_por_nome(nome: str, uf: str | None = None) -> CnefeMunicipio | None:
    """Homônimo sem UF fica sem resposta de propósito: chutar entre as sete "Bom Jesus"
    do país devolveria ruas reais do município errado, que é justamente o erro a evitar."""
    alvo = termos.normalizar(nome or "")
    if not alvo:
        return None
    tabela = _municipios()
    candidatos = tabela.get(alvo)
    if not candidatos:
        parecidos = [(SequenceMatcher(None, alvo, chave).ratio(), linhas)
                     for chave, linhas in tabela.items()
                     if abs(len(chave) - len(alvo)) <= 3]
        melhor = max(parecidos, default=None, key=lambda p: p[0])
        if melhor is None or melhor[0] < SIM_MUNICIPIO_MIN:
            return None
        candidatos = melhor[1]
    if uf:
        candidatos = [r for r in candidatos if r["uf"] == uf.upper()]
    if len(candidatos) != 1:
        return None
    return _para_municipio(candidatos[0])


def _interpolar(row: sqlite3.Row, numero: int | None) -> tuple[float, float, bool]:
    """Posiciona a casa entre as duas pontas da numeração e diz se o número existe
    na faixa cadastrada. Só vale para a base v1, que não guarda casa por casa.

    Medido em 1.157 casas do Acre: em rua compacta o erro cai de 61 m para 35 m, mas
    em via que estourou o raio — rodovia, ramal, estrada — a numeração não acompanha
    a geografia e interpolar piorou de 3.632 m para 4.266 m. Lá fica o centroide.
    """
    lat, lon = row["lat"] / 1e6, row["lon"] / 1e6
    nmin, nmax = row["num_min"], row["num_max"]
    if numero is None or nmin is None or nmax is None or nmin == nmax:
        return lat, lon, False
    na_faixa = nmin <= numero <= nmax
    if row["raio_m"] >= RAIO_TETO_M:
        return lat, lon, na_faixa
    t = min(1.0, max(0.0, (numero - nmin) / (nmax - nmin)))
    lat_min, lon_min = lat + row["dlat_min"] / 1e6, lon + row["dlon_min"] / 1e6
    lat_max, lon_max = lat + row["dlat_max"] / 1e6, lon + row["dlon_max"] / 1e6
    return lat_min + t * (lat_max - lat_min), lon_min + t * (lon_max - lon_min), na_faixa


class Posicao(NamedTuple):
    lat: float
    lon: float
    status: NumeroStatus
    num_antes: int | None = None
    num_depois: int | None = None
    aproximada: bool = False
    n_numeros: int = 0


def _ler_varint(dados: bytes, pos: int) -> tuple[int, int]:
    valor = deslocamento = 0
    while True:
        b = dados[pos]
        pos += 1
        valor |= (b & 127) << deslocamento
        if b < 128:
            return valor, pos
        deslocamento += 7


def _decodificar(dados: bytes, n: int, lat0_e6: int, lon0_e6: int
                 ) -> tuple[list[int], list[tuple[float, float, bool]]]:
    """Desfaz o blob gravado por `build_cnefe.codificar_numeracao`.

    A âncora dos deltas é o centroide da própria linha do logradouro, que por isso não
    viaja no blob — e é também por isso que ela tem de ser o inteiro guardado na tabela.
    """
    numeros: list[int] = []
    pontos: list[tuple[float, float, bool]] = []
    pos = numero = 0
    qlat = round(lat0_e6 / QUANT_E6)
    qlon = round(lon0_e6 / QUANT_E6)
    for _ in range(n):
        cabeca, pos = _ler_varint(dados, pos)
        delta = cabeca >> 1
        numero = delta if numero == 0 else numero + delta + 1
        z, pos = _ler_varint(dados, pos)
        qlat += (z >> 1) ^ -(z & 1)
        z, pos = _ler_varint(dados, pos)
        qlon += (z >> 1) ^ -(z & 1)
        numeros.append(numero)
        pontos.append((qlat * QUANT_E6 / 1e6, qlon * QUANT_E6 / 1e6, bool(cabeca & 1)))
    return numeros, pontos


def _numeros(log_id: int, lat0_e6: int, lon0_e6: int
             ) -> tuple[list[int], list[tuple[float, float, bool]]]:
    cache: dict[int, tuple] = _memo.setdefault("numeracao", {})
    pronto = cache.get(log_id)
    if pronto is not None:
        return pronto

    con = _conexao()
    row = (con.execute("SELECT n, dados FROM numeracao WHERE log_id = ?",
                       (log_id,)).fetchone() if con is not None else None)
    pronto = (_decodificar(row["dados"], row["n"], lat0_e6, lon0_e6) if row is not None
              else ([], []))
    if len(cache) >= NUMERACAO_EM_CACHE:
        cache.pop(next(iter(cache), None), None)
    cache[log_id] = pronto
    return pronto


def posicionar(row: sqlite3.Row, numero: int | None) -> Posicao:
    """Onde fica a casa nesta rua, e o quanto disso é cadastro e o quanto é palpite.

    Com a numeração real (base v2) o número cadastrado devolve a coordenada que o
    recenseador anotou na porta. O que não está cadastrado sai da reta entre os dois
    vizinhos, sem separar par de ímpar: os dois lados da rua distam 10–15 m, menos que
    o salto para um número mais distante do mesmo lado — restringir à paridade piorou o
    p75 de 86 m para 101 m no Espírito Santo.
    """
    lat, lon = row["lat"] / 1e6, row["lon"] / 1e6
    if numero is None:
        return Posicao(lat, lon, "sem_numero")
    if not tem_numeracao():
        ilat, ilon, na_faixa = _interpolar(row, numero)
        return Posicao(ilat, ilon, "faixa" if na_faixa else "fora",
                       row["num_min"], row["num_max"])

    numeros, pontos = _numeros(row["id"], row["lat"], row["lon"])
    if not numeros:
        return Posicao(lat, lon, "sem_numeracao")
    n = len(numeros)
    i = bisect_left(numeros, numero)
    if i < n and numeros[i] == numero:
        plat, plon, aprox = pontos[i]
        return Posicao(plat, plon, "exato", numero, numero, aprox, n)

    # Daqui para baixo a coordenada é deduzida, e a guarda das vias quilométricas volta
    # a valer: em rodovia e ramal a numeração não acompanha a geografia, e deduzir por
    # ela joga a casa quilômetros adiante. No ramo `exato` acima ela não se aplica —
    # aquela coordenada foi medida, não deduzida.
    fora_da_faixa = i == 0 or i == n
    antes = numeros[i - 1] if i > 0 else None
    depois = numeros[i] if i < n else None
    if row["raio_m"] >= RAIO_TETO_M:
        return Posicao(lat, lon, "fora" if fora_da_faixa else "vizinho",
                       antes, depois, False, n)
    if fora_da_faixa:
        plat, plon, aprox = pontos[0] if i == 0 else pontos[-1]
        return Posicao(plat, plon, "fora", antes, depois, aprox, n)
    lat_a, lon_a, apr_a = pontos[i - 1]
    lat_b, lon_b, apr_b = pontos[i]
    t = (numero - antes) / (depois - antes)
    return Posicao(lat_a + t * (lat_b - lat_a), lon_a + t * (lon_b - lon_a),
                   "vizinho", antes, depois, apr_a or apr_b, n)


def _rotular(row: sqlite3.Row, municipio: CnefeMunicipio | None) -> str:
    tipo = _tipos().get(row["tipo"], "")
    partes = [f"{tipo.title()} {row['nome']}".strip().title()]
    if municipio:
        partes.append(f"{municipio.nome} - {municipio.uf}" if municipio.uf else municipio.nome)
    return ", ".join(partes)


def _cobre(tokens: list[str], nome: str) -> bool:
    """Toda palavra procurada começa alguma palavra do nome — busca por parte da rua."""
    palavras = nome.split()
    return all(any(p.startswith(t) for p in palavras) for t in tokens)


class _Pontuado(NamedTuple):
    sim: float
    tipo_bate: bool
    cep_bate: bool
    n_end: int
    row: sqlite3.Row
    cep: str | None


def _candidatos(via: str, linhas: list[sqlite3.Row],
                postings: dict[str, list[int]]) -> set[int]:
    teto = max(50, int(len(linhas) * FRACAO_TOKEN_INUTIL))
    postagens = []
    for token in set(via.split()):
        # O prefixo só entra quando a palavra inteira não existe na base: em São Paulo
        # "paul" traz milhares de ruas e o comparador caro rodaria em todas à toa.
        posting = postings.get(token) or postings.get(token[:4])
        if posting and len(posting) <= teto:
            postagens.append(posting)
    escolhidos: set[int] = set()
    # Do token mais raro para o mais comum: "setembro" aponta cinco ruas e "de" mil,
    # e rua que só compartilhe "de" com a busca nunca chegaria ao piso de similaridade.
    for posting in sorted(postagens, key=len):
        if escolhidos and len(escolhidos) + len(posting) > CANDIDATOS_MAX:
            break
        escolhidos.update(posting)
    return escolhidos


def _pontuar(rows, via: str, tipo_alvo: str, cep_alvo: str,
             tipos: dict[int, str]) -> list[_Pontuado]:
    achados = []
    tokens = via.split()
    # `set_seq2` uma vez só: o difflib indexa a segunda sequência e reaproveita esse
    # trabalho a cada `set_seq1`, que é o lado que muda.
    comparador = SequenceMatcher(None)
    comparador.set_seq2(via)
    for row in rows:
        nome = row["nome"]
        comparador.set_seq1(nome)
        # Quem digita "alfredo" procurando "Alfredo Guedes" fica em 0,67 e seria cortado.
        # A rua entra na lista, mas com a similaridade real: 0,67 não seleciona sozinho,
        # e é isso que se quer — a escolha volta para o usuário.
        cobre = _cobre(tokens, nome)
        # Os dois `quick` são tetos baratos da razão; quando nem eles alcançam o piso,
        # calculá-la de verdade seria trabalho jogado fora.
        if not cobre and (comparador.real_quick_ratio() < SIM_MIN
                          or comparador.quick_ratio() < SIM_MIN):
            continue
        sim = comparador.ratio()
        if sim < SIM_MIN and not cobre:
            continue
        cep_row = str(row["cep"]).zfill(8) if row["cep"] else None
        tipo_bate = bool(tipo_alvo) and termos.normalizar(tipos.get(row["tipo"], "")) == tipo_alvo
        achados.append(_Pontuado(sim, tipo_bate, cep_row == cep_alvo, row["n_end"],
                                 row, cep_row))
    return achados


def buscar_logradouro(logradouro: str, *, cod_ibge: str | None = None,
                      cep: str | None = None, municipio: str | None = None,
                      uf: str | None = None, numero: int | None = None,
                      limite: int = 8) -> list[CnefeLogradouro]:
    """As ruas de um município que se parecem com o texto lido, da melhor para a pior.

    Sem município identificado devolve vazio em vez de varrer o país: uma "Rua São
    José" existe em milhares de cidades e propor todas seria pior que não propor nada.
    """
    tipo_alvo, via, _ = _separar_tipo(logradouro or "")
    if not via:
        return []

    muni = resolver_municipio(cod_ibge, cep, municipio, uf)
    if muni is None:
        return []
    carregado = _indice(int(muni.cod_ibge))
    if carregado is None:
        return []
    linhas, postings = carregado
    candidatos = _candidatos(via, linhas, postings)
    if not candidatos:
        return []

    tipos = _tipos()
    achados = _pontuar((linhas[i] for i in candidatos), via, tipo_alvo,
                       normalizar_cep(cep or "") or "", tipos)
    achados.sort(key=lambda p: (round(p.sim, 2), p.tipo_bate, p.cep_bate, p.n_end),
                 reverse=True)
    # A numeração só é lida depois do corte: são poucas leituras de blob por busca, e
    # não uma por candidato pontuado.
    return [_para_logradouro(p.row, muni, tipos, p.cep, numero, p.sim)
            for p in achados[:limite]]


def municipios_perto(lat: float, lon: float, *, limite: int = 12,
                     raio_m: float = 60_000) -> list[CnefeMunicipio]:
    """Os municípios que podem alcançar este ponto, do mais próximo ao mais distante.

    A distância é até a borda do disco do município, não até o centroide: um município
    amazônico tem 80 km de raio e já contém o foco muito antes de o centroide dele
    chegar perto.
    """
    perto = []
    # 80 km é o teto do raio de município que o build aplica, então nada além desta
    # faixa de latitude pode alcançar o foco.
    graus = (raio_m + 80_000) / 111_320
    for row in _municipios_lista():
        # Descarte por latitude antes da haversine: são 5.570 municípios a cada tecla.
        if abs(lat - row["lat"] / 1e6) > graus:
            continue
        d = distancia_m(lat, lon, row["lat"] / 1e6, row["lon"] / 1e6)
        borda = max(0.0, d - row["raio_m"])
        if borda <= raio_m:
            perto.append((borda, d, row))
    # O centroide desempata: vários discos contêm o foco e todos ficam com borda zero,
    # mas o primeiro da lista é o que ganha o índice invertido completo, e esse tem de
    # ser a cidade onde o ponto está de fato — não a de maior raio.
    perto.sort(key=lambda p: (p[0], p[1]))
    return [_para_municipio(row) for _, _, row in perto[:limite]]


def buscar_perto(logradouro: str, lat: float, lon: float, *, numero: int | None = None,
                 limite: int = 10) -> list[CnefeLogradouro]:
    """As ruas parecidas com o texto na vizinhança de um ponto — para a caixa de busca
    do painel, onde ninguém digita a cidade.

    O município do foco usa o índice invertido inteiro, que casa o texto no meio do
    nome; os vizinhos usam range scan na própria chave primária, que só casa quem
    digitou o começo. Montar o índice dos doze municípios custaria centenas de
    milissegundos por tecla, e numa caixa de busca a pessoa digita o começo do nome —
    ao contrário do OCR sujo, que é o caso que o modal de importação trata.
    """
    tipo_alvo, via, _ = _separar_tipo(logradouro or "")
    con = _conexao()
    if not via or con is None:
        return []
    tipos = _tipos()
    campos = ",".join(_campos_log())
    achados: list[tuple] = []
    for pos, muni in enumerate(municipios_perto(lat, lon)):
        if pos == 0:
            carregado = _indice(int(muni.cod_ibge))
            if carregado is None:
                continue
            linhas, postings = carregado
            rows = [linhas[i] for i in _candidatos(via, linhas, postings)]
        else:
            rows = con.execute(
                f"SELECT {campos} FROM logradouro "
                "WHERE cod_ibge = ? AND nome >= ? AND nome < ?",
                (int(muni.cod_ibge), via, via + FIM_DO_PREFIXO)).fetchall()
        for p in _pontuar(rows, via, tipo_alvo, "", tipos):
            d = distancia_m(lat, lon, p.row["lat"] / 1e6, p.row["lon"] / 1e6)
            achados.append((p, d, muni))

    # Uma lista só, ordenada pela distância da rua ao foco — não pela do município, que
    # colocaria o centro de uma cidade vizinha na frente da rua do bairro ao lado. Os
    # 5 km de granularidade impedem que meio quilômetro derrube um casamento melhor.
    achados.sort(key=lambda a: (round(a[0].sim, 2), a[0].tipo_bate,
                                -int(a[1] // 5000), a[0].n_end), reverse=True)
    return [_para_logradouro(p.row, muni, tipos, p.cep, numero, p.sim, d)
            for p, d, muni in achados[:limite]]


def _para_logradouro(row: sqlite3.Row, muni: CnefeMunicipio, tipos: dict[int, str],
                     cep_row: str | None, numero: int | None, sim: float,
                     distancia: float | None = None) -> CnefeLogradouro:
    pos = posicionar(row, numero)
    return CnefeLogradouro(
        cod_ibge=muni.cod_ibge, nome=row["nome"], tipo=tipos.get(row["tipo"]),
        label=_rotular(row, muni), lat=pos.lat, lon=pos.lon, raio_m=row["raio_m"],
        n_enderecos=row["n_end"], cep=cep_row,
        num_min=row["num_min"], num_max=row["num_max"],
        numero=numero, numero_confirmado=pos.status == "exato",
        numero_status=pos.status, num_antes=pos.num_antes, num_depois=pos.num_depois,
        n_numeros=pos.n_numeros, coordenada_aproximada=pos.aproximada,
        distancia_m=distancia, similaridade=round(sim, 3), municipio=muni,
    )


def resolver_municipio(cod_ibge: str | None = None, cep: str | None = None,
                       municipio: str | None = None, uf: str | None = None
                       ) -> CnefeMunicipio | None:
    if cod_ibge:
        return lookup_municipio(str(cod_ibge))
    if cep:
        achado = lookup(cep)
        if achado and achado.municipio:
            return achado.municipio
    if municipio:
        return municipio_por_nome(municipio, uf)
    return None
