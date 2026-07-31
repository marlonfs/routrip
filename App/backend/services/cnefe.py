"""Consulta à base local do CNEFE/IBGE.

Duas perguntas: "onde fica este CEP?" e "esta rua existe neste município?". A segunda
é a que permite só oferecer ao usuário endereços que existem de verdade.

A base é opcional. Sem ela o app continua funcionando — a validação de endereço
apenas perde a âncora geográfica e passa a depender só do ViaCEP.
"""

import math
import sqlite3
import threading
from difflib import SequenceMatcher

from core.paths import cnefe_db
from core.schemas import CnefeCep, CnefeLogradouro, CnefeMunicipio, CnefeStatus
from services import br_address_terms as termos

_local = threading.local()

_CAMPOS_CEP = ("cep", "lat", "lon", "raio_m", "generico", "n_enderecos",
               "logradouro", "localidade", "cod_ibge")

# Medido sobre as 300 ruas mais movimentadas de Piracicaba: de 0,60 a 0,80 o acerto com
# texto corrompido fica em 96%, mas só a partir de 0,70 nenhuma rua inventada recebe
# resposta. Abaixo disso "Rua Inventada Que Não Existe" casava com "Avenida Investigador
# Lucídio Leite" — exatamente o que não pode ser oferecido.
SIM_MIN = 0.7
SIM_MUNICIPIO_MIN = 0.85
MUNICIPIOS_EM_CACHE = 3
# Mesmo teto que o build aplica ao raio: quem chegou nele é via de dezenas de
# quilômetros, sem posição confiável para o número.
RAIO_TETO_M = 5000
# Token presente em boa parte das ruas do município ("dos", "santos") não separa nada
# e traz milhares de candidatos para o comparador caro.
FRACAO_TOKEN_INUTIL = 0.3
# Teto de linhas comparadas por busca. "Rua Sete De Setembro" unia o posting de "de"
# — mil ruas em Piracicaba — e a busca levava 20 ms em vez de 0,4 ms.
CANDIDATOS_MAX = 400


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
    """Chamado após regravar o arquivo, para que a próxima consulta reabra a base."""
    con = getattr(_local, "con", None)
    if con is not None:
        con.close()
        _local.con = None


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
    con = _conexao()
    if con is None:
        return {}
    return {k: v for k, v in con.execute("SELECT chave, valor FROM meta")}


def busca_por_rua() -> bool:
    """Uma base gerada antes do índice tem as tabelas de CEP idênticas e passaria
    despercebida; só a chave em `meta` distingue as duas."""
    return bool(_meta().get("versao_indice"))


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
        busca_por_rua=bool(meta.get("versao_indice")),
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


def _tipos() -> dict[int, str]:
    tipos = getattr(_local, "tipos", None)
    if tipos is None:
        con = _conexao()
        tipos = ({i: nome for i, nome in con.execute("SELECT id, nome FROM tipo_logradouro")}
                 if con is not None else {})
        _local.tipos = tipos
    return tipos


def _tipos_por_nome() -> tuple[dict[str, int], int]:
    """Vocabulário de tipos do próprio CNEFE — 390 deles, contra a dúzia que o parser de
    endereço reconhece. Sem consultá-lo, "Caminho 1" (979 casas em Salvador) não acha
    nada, porque na base essa linha ficou só como "1", com o tipo guardado à parte."""
    pronto = getattr(_local, "tipos_nome", None)
    if pronto is None:
        vocab = {termos.normalizar(nome): i for i, nome in _tipos().items() if nome}
        pronto = (vocab, max((len(n.split()) for n in vocab), default=1))
        _local.tipos_nome = pronto
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
    cache: dict[int, tuple] = getattr(_local, "indices", None) or {}
    _local.indices = cache
    pronto = cache.get(cod_ibge)
    if pronto is not None:
        return pronto

    con = _conexao()
    if con is None:
        return None
    linhas = con.execute(
        f"SELECT {','.join(_CAMPOS_LOG)} FROM logradouro WHERE cod_ibge = ?", (cod_ibge,)
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

    if len(cache) >= MUNICIPIOS_EM_CACHE:
        cache.pop(next(iter(cache)))
    cache[cod_ibge] = (linhas, postings)
    return cache[cod_ibge]


def _municipios() -> dict[str, list[sqlite3.Row]]:
    """Os 5.570 municípios cabem folgados na memória e a busca por nome é frequente."""
    por_nome = getattr(_local, "municipios", None)
    if por_nome is not None:
        return por_nome
    con = _conexao()
    por_nome = {}
    if con is not None:
        for row in con.execute("SELECT cod_ibge, nome, uf, lat, lon, raio_m, n_ceps "
                               "FROM municipio WHERE nome IS NOT NULL"):
            por_nome.setdefault(termos.normalizar(row["nome"]), []).append(row)
    _local.municipios = por_nome
    return por_nome


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
    na faixa cadastrada.

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

    teto = max(50, int(len(linhas) * FRACAO_TOKEN_INUTIL))
    postagens = []
    for token in set(via.split()):
        # O prefixo só entra quando a palavra inteira não existe na base: em São Paulo
        # "paul" traz milhares de ruas e o comparador caro rodaria em todas à toa.
        posting = postings.get(token) or postings.get(token[:4])
        if posting and len(posting) <= teto:
            postagens.append(posting)
    candidatos: set[int] = set()
    # Do token mais raro para o mais comum: "setembro" aponta cinco ruas e "de" mil,
    # e rua que só compartilhe "de" com a busca nunca chegaria ao piso de similaridade.
    for posting in sorted(postagens, key=len):
        if candidatos and len(candidatos) + len(posting) > CANDIDATOS_MAX:
            break
        candidatos.update(posting)
    if not candidatos:
        return []

    cep_alvo = normalizar_cep(cep or "") or ""
    tipos = _tipos()
    achados = []
    tokens = via.split()
    # `set_seq2` uma vez só: o difflib indexa a segunda sequência e reaproveita esse
    # trabalho a cada `set_seq1`, que é o lado que muda.
    comparador = SequenceMatcher(None)
    comparador.set_seq2(via)
    for i in candidatos:
        row = linhas[i]
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
        achados.append((round(sim, 2), tipo_bate, cep_row == cep_alvo, row["n_end"],
                        sim, row, cep_row))
    if not achados:
        return []

    achados.sort(key=lambda a: a[:4], reverse=True)
    saida = []
    for *_, sim, row, cep_row in achados[:limite]:
        lat, lon, confirmado = _interpolar(row, numero)
        saida.append(CnefeLogradouro(
            cod_ibge=muni.cod_ibge, nome=row["nome"], tipo=tipos.get(row["tipo"]),
            label=_rotular(row, muni), lat=lat, lon=lon, raio_m=row["raio_m"],
            n_enderecos=row["n_end"], cep=cep_row,
            num_min=row["num_min"], num_max=row["num_max"],
            numero=numero, numero_confirmado=confirmado,
            similaridade=round(sim, 3), municipio=muni,
        ))
    return saida


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
