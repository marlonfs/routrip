"""Gera cnefe.sqlite a partir dos microdados do CNEFE/Censo 2022 do IBGE.

Três agregações do mesmo passeio pelos CSVs:

- por CEP, guardando centroide, raio e o logradouro/localidade/município predominantes;
- por (município, logradouro), que é o que permite responder "esta rua existe?" antes
  de propor um endereço ao usuário. Sem ela só dava para validar quem trouxesse CEP —
  e 4.490 dos 5.570 municípios têm menos de cinco CEPs na base;
- por (logradouro, número), que guarda a coordenada de cada casa cadastrada. Sem ela
  sobrava interpolar entre as duas pontas da rua, o que erra 105 m na mediana e 2,4 km
  no p90 (medido no Espírito Santo contra a coordenada real).

    python tools/build_cnefe.py --out backend/vendor/cnefe.sqlite

O agregado oficial "Agregados_por_CEP" NÃO serve aqui: traz só contagens de
domicílios, sem coordenada nenhuma. E "Coordenadas_enderecos" traz coordenada sem
CEP. Só o microdado completo tem as duas coisas na mesma linha.
"""

import argparse
import csv
import gzip
import io
import json
import math
import shutil
import sqlite3
import sys
import time
import urllib.request
import zipfile
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services import br_address_terms as termos  # noqa: E402

FTP = ("https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos"
       "/Censo_Demografico_2022/Arquivos_CNEFE/CSV/UF/")
MUNICIPIOS_API = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"

UFS = [
    "11_RO", "12_AC", "13_AM", "14_RR", "15_PA", "16_AP", "17_TO", "21_MA", "22_PI",
    "23_CE", "24_RN", "25_PB", "26_PE", "27_AL", "28_SE", "29_BA", "31_MG", "32_ES",
    "33_RJ", "35_SP", "41_PR", "42_SC", "43_RS", "50_MS", "51_MT", "52_GO", "53_DF",
]

COLUNAS = ("CEP", "COD_MUNICIPIO", "DSC_LOCALIDADE", "NOM_TIPO_SEGLOGR",
           "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR", "NUM_ENDERECO", "LATITUDE", "LONGITUDE",
           "NV_GEO_COORD")

RAIO_MIN_M = 250.0
RAIO_MAX_M = 5000.0
GRAU_EM_METROS = 111320.0

# Passo da quantização das coordenadas da numeração, em micrograus: 11 µ° ≈ 1,22 m, com
# erro máximo de ±0,61 m por eixo. Some isso aos 4 m de mediana que separam as unidades
# de um mesmo número (apartamento, fundos, comércio) e o arredondamento some no ruído.
QUANT_E6 = 11
# Do 3 em diante o CNEFE não capturou a coordenada na porta, e sim na face de quadra ou
# em algo mais grosso. Serve para escolher a melhor linha dentro de um mesmo número.
NV_APROXIMADO = 3


class Maioria:
    """Boyer-Moore: guarda o valor predominante em memória constante. Um CEP tem
    dezenas de milhares de linhas e quase sempre um único logradouro — contar todas
    as variantes custaria gigabytes para um empate que não existe."""

    __slots__ = ("valor", "peso")

    def __init__(self) -> None:
        self.valor: str = ""
        self.peso: int = 0

    def add(self, v: str) -> None:
        if not v:
            return
        if self.valor == v:
            self.peso += 1
        elif self.peso == 0:
            self.valor, self.peso = v, 1
        else:
            self.peso -= 1


class Nuvem:
    """Centroide e dispersão de um conjunto de pontos sem guardar os pontos."""

    __slots__ = ("n", "slat", "slon", "slat2", "slon2")

    def __init__(self) -> None:
        self.n = 0
        self.slat = self.slon = self.slat2 = self.slon2 = 0.0

    def add(self, lat: float, lon: float) -> None:
        self.n += 1
        self.slat += lat
        self.slon += lon
        self.slat2 += lat * lat
        self.slon2 += lon * lon

    def centroide(self) -> tuple[float, float]:
        return self.slat / self.n, self.slon / self.n

    def raio_bruto_m(self) -> float:
        """2 desvios-padrão da nuvem de endereços. Cobre a rua inteira sem inflar
        com o outlier de digitação que todo cadastro tem."""
        if self.n < 2:
            return RAIO_MIN_M
        lat, lon = self.centroide()
        var_lat = max(0.0, self.slat2 / self.n - lat * lat)
        var_lon = max(0.0, self.slon2 / self.n - lon * lon)
        dp_lat = math.sqrt(var_lat) * GRAU_EM_METROS
        dp_lon = math.sqrt(var_lon) * GRAU_EM_METROS * math.cos(math.radians(lat))
        return 2.0 * math.hypot(dp_lat, dp_lon)


class Agregado(Nuvem):
    __slots__ = ("logradouro", "localidade", "municipio")

    def __init__(self) -> None:
        super().__init__()
        self.logradouro = Maioria()
        self.localidade = Maioria()
        self.municipio = Maioria()


class AgregadoLog(Nuvem):
    """Um logradouro de um município. As pontas guardam onde ficam o menor e o maior
    número encontrados; `nums` guarda todas as casas, três inteiros por linha lida.

    As pontas continuam sendo gravadas mesmo com `nums`: elas são o que um aplicativo
    antigo lê, e o que responde por uma rua cuja numeração não coube no critério.
    """

    __slots__ = ("cep", "num_min", "num_max", "ponta_min", "ponta_max", "nums")

    def __init__(self) -> None:
        super().__init__()
        self.cep = Maioria()
        self.num_min: int | None = None
        self.num_max: int | None = None
        self.ponta_min: tuple[float, float] | None = None
        self.ponta_max: tuple[float, float] | None = None
        # Criado só na primeira casa numerada: um quarto das ruas do país não tem
        # nenhuma, e um array vazio por rua custaria 30 MB de objetos à toa.
        self.nums: array | None = None

    def numerar(self, numero: int, lat: float, lon: float) -> None:
        if self.num_min is None or numero < self.num_min:
            self.num_min, self.ponta_min = numero, (lat, lon)
        if self.num_max is None or numero > self.num_max:
            self.num_max, self.ponta_max = numero, (lat, lon)

    def anotar_numero(self, numero: int, lat_e6: int, lon_e6: int, nv: int) -> None:
        """Empilha a casa crua. O agrupamento por número fica para o flush da UF, uma
        rua de cada vez — o CSV alterna de município a cada punhado de linhas (1,87 mi
        de trocas nas primeiras 3 mi de linhas de São Paulo), então agrupar durante a
        leitura exigiria segurar o país inteiro num dicionário aninhado."""
        if self.nums is None:
            self.nums = array("i")
        # O nível de qualidade viaja nos três bits baixos: são 12 B por casa em vez de
        # 16, e em São Paulo essa diferença é de 66 MB de pico.
        self.nums.append(numero * 8 + nv)
        self.nums.append(lat_e6)
        self.nums.append(lon_e6)


def _baixar(nome: str, cache: Path | None) -> Path | None:
    url = FTP + nome + ".zip"
    if cache is None:
        return None
    destino = cache / f"{nome}.zip"
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    parcial = destino.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=600) as r, open(parcial, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    parcial.replace(destino)
    return destino


def _abrir_csv(nome: str, cache: Path | None):
    caminho = _baixar(nome, cache)
    if caminho is not None:
        z = zipfile.ZipFile(caminho)
    else:
        with urllib.request.urlopen(FTP + nome + ".zip", timeout=600) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
    interno = z.infolist()[0].filename
    return z, io.TextIOWrapper(z.open(interno), encoding="latin-1", newline="")


def _juntar_logradouro(tipo: str, titulo: str, nome: str) -> str:
    return " ".join(p for p in (tipo.strip(), titulo.strip(), nome.strip()) if p)


def _numero(bruto: str) -> int | None:
    """Zero é como o CNEFE grava "sem número" — 83% das linhas do Acre — e seis dígitos
    é sempre erro de cadastro. Os dois puxariam a ponta da rua para o lugar errado."""
    bruto = bruto.strip()
    if not bruto.isdigit() or len(bruto) > 5:
        return None
    return int(bruto) or None


def _nivel_geo(bruto: str) -> int:
    """NV_GEO_COORD, saturado nos três bits que sobram no inteiro do número. Ausente ou
    ilegível vira 7, o pior nível: na dúvida, a linha perde de qualquer outra."""
    bruto = bruto.strip()
    return min(int(bruto), 7) if bruto.isdigit() else 7


def _varint(v: int, saida: bytearray) -> None:
    while v >= 128:
        saida.append((v & 127) | 128)
        v >>= 7
    saida.append(v)


def _zigzag(v: int) -> int:
    return (v << 1) ^ (v >> 63)


def _mediana(valores: list[int]) -> int:
    """Mediana, e não média: as unidades de um mesmo número se espalham por 109 m no
    p90 (prédio com portaria nos fundos, condomínio), e a média cairia no meio do
    terreno. A mediana devolve a coordenada de uma unidade que existe."""
    return sorted(valores)[len(valores) // 2]


def codificar_numeracao(nums: array, lat0_e6: int, lon0_e6: int) -> tuple[int, bytes]:
    """As casas de uma rua num blob: (número, latitude, longitude) por delta, em varint.

    Três decisões que valem 40% do tamanho, medidas nos 739.784 números do Espírito
    Santo: a âncora é o centroide já gravado na linha do logradouro (não vai no blob);
    a flag de coordenada aproximada viaja no bit 0 do delta do número, onde não custa
    byte nenhum porque o delta típico é de 1 a 20; e as coordenadas são quantizadas em
    1,22 m. Assim o número sai por 3,46 bytes, contra 4,72 da forma direta.
    """
    casas: dict[int, tuple[list[int], list[int], int]] = {}
    for i in range(0, len(nums), 3):
        chave = nums[i]
        numero, nv = chave >> 3, chave & 7
        atual = casas.get(numero)
        if atual is None or nv < atual[2]:
            # Nível melhor descarta o que veio antes: coordenada de porta e coordenada
            # de face de quadra na mesma pilha dariam uma mediana sem sentido.
            casas[numero] = ([nums[i + 1]], [nums[i + 2]], nv)
        elif nv == atual[2]:
            atual[0].append(nums[i + 1])
            atual[1].append(nums[i + 2])

    saida = bytearray()
    ant_num = 0
    ant_lat = round(lat0_e6 / QUANT_E6)
    ant_lon = round(lon0_e6 / QUANT_E6)
    for numero in sorted(casas):
        lats, lons, nv = casas[numero]
        qlat = round(_mediana(lats) / QUANT_E6)
        qlon = round(_mediana(lons) / QUANT_E6)
        # Os números são crescentes e distintos, então o -1 aproveita o valor que a
        # diferença nunca assume e faz a rua de numeração contínua caber em 1 byte.
        delta = numero - ant_num - 1 if ant_num else numero
        _varint((delta << 1) | (1 if nv >= NV_APROXIMADO else 0), saida)
        _varint(_zigzag(qlat - ant_lat), saida)
        _varint(_zigzag(qlon - ant_lon), saida)
        ant_num, ant_lat, ant_lon = numero, qlat, qlon
    return len(casas), bytes(saida)


def processar_uf(nome: str, dados: dict[str, Agregado],
                 logs: dict[tuple, AgregadoLog], tipos: dict[str, int],
                 cache: Path | None, passe: int = 0, n_passes: int = 1) -> int:
    z, texto = _abrir_csv(nome, cache)
    linhas = 0
    # Cada nome de rua reaparece dezenas de vezes no arquivo; normalizar é caro
    # (NFKD char a char) e sem memoizar dominaria o tempo das 111 milhões de linhas.
    normalizados: dict[str, str] = {}
    try:
        leitor = csv.reader(texto, delimiter=";")
        cabecalho = next(leitor)
        try:
            idx = [cabecalho.index(c) for c in COLUNAS]
        except ValueError:
            raise SystemExit(f"{nome}: colunas esperadas ausentes. Lido: {cabecalho}")
        i_cep, i_mun, i_loc, i_tipo, i_titulo, i_nome, i_num, i_lat, i_lon, i_nv = idx

        for row in leitor:
            linhas += 1
            try:
                lat = float(row[i_lat])
                lon = float(row[i_lon])
            except (IndexError, ValueError):
                continue

            # Um município cai sempre no mesmo passe, então dividir por ele reparte as
            # linhas sem quebrar nenhum agregado — inclusive os do CEP, que atravessam
            # o laço das UFs. Ver --num-passes.
            if n_passes > 1 and int(row[i_mun]) % n_passes != passe:
                continue

            cep = row[i_cep]
            if len(cep) != 8 or not cep.isdigit():
                cep = ""
            if cep:
                ag = dados.get(cep)
                if ag is None:
                    ag = dados[cep] = Agregado()
                ag.add(lat, lon)
                ag.municipio.add(row[i_mun])
                ag.localidade.add(row[i_loc])
                ag.logradouro.add(_juntar_logradouro(row[i_tipo], row[i_titulo], row[i_nome]))

            # O logradouro entra mesmo sem CEP válido: na zona rural o cadastro vem
            # sem CEP e a rua existe do mesmo jeito.
            bruto = _juntar_logradouro("", row[i_titulo], row[i_nome])
            via = normalizados.get(bruto)
            if via is None:
                via = normalizados[bruto] = termos.normalizar(bruto)
            if not via:
                continue
            tipo = row[i_tipo].strip().upper()
            id_tipo = tipos.get(tipo)
            if id_tipo is None:
                id_tipo = tipos[tipo] = len(tipos) + 1
            chave = (row[i_mun], via, id_tipo)
            lg = logs.get(chave)
            if lg is None:
                lg = logs[chave] = AgregadoLog()
            lg.add(lat, lon)
            if cep:
                lg.cep.add(cep)
            num = _numero(row[i_num])
            if num is not None:
                lg.numerar(num, lat, lon)
                lg.anotar_numero(num, round(lat * 1e6), round(lon * 1e6),
                                 _nivel_geo(row[i_nv]))
    finally:
        texto.close()
        z.close()
    return linhas


def _uf_do_municipio(m: dict) -> str | None:
    micro = m.get("microrregiao")
    if micro:
        return micro["mesorregiao"]["UF"]["sigla"]
    imediata = m.get("regiao-imediata")
    if imediata:
        return imediata["regiao-intermediaria"]["UF"]["sigla"]
    return None


def nomes_de_municipio() -> dict[str, tuple[str, str]]:
    with urllib.request.urlopen(MUNICIPIOS_API, timeout=120) as r:
        bruto = r.read()
    if bruto[:2] == b"\x1f\x8b":  # a API responde gzip mesmo sem Accept-Encoding
        bruto = gzip.decompress(bruto)
    crus = json.loads(bruto.decode("utf-8"))
    saida = {}
    for m in crus:
        uf = _uf_do_municipio(m)
        if uf:
            saida[str(m["id"])] = (m["nome"], uf)
    return saida


def criar_base(tmp: Path) -> sqlite3.Connection:
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript("""
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        CREATE TABLE cep (
            cep TEXT PRIMARY KEY, lat INTEGER, lon INTEGER, raio_m INTEGER,
            generico INTEGER, n_enderecos INTEGER, logradouro TEXT,
            localidade TEXT, cod_ibge TEXT
        );
        CREATE TABLE municipio (
            cod_ibge TEXT PRIMARY KEY, nome TEXT, uf TEXT,
            lat INTEGER, lon INTEGER, raio_m INTEGER, n_ceps INTEGER, n_log INTEGER
        );
        CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT);
        -- Sem rowid: a chave primária já ordena a tabela por município, que é como
        -- toda consulta chega. Um índice à parte custaria 25 B por linha, 55 MB no
        -- Brasil, para repetir o que a tabela já faz.
        --
        -- num_min/num_max e as pontas viraram peso morto com a tabela numeracao, mas
        -- ficam: uma versão antiga do aplicativo abrindo esta base morreria com
        -- "no such column".
        CREATE TABLE logradouro (
            cod_ibge INTEGER, nome TEXT, tipo INTEGER,
            n_end INTEGER, cep INTEGER, lat INTEGER, lon INTEGER, raio_m INTEGER,
            num_min INTEGER, num_max INTEGER,
            dlat_min INTEGER, dlon_min INTEGER, dlat_max INTEGER, dlon_max INTEGER,
            id INTEGER,
            PRIMARY KEY (cod_ibge, nome, tipo)
        ) WITHOUT ROWID;
        -- log_id é alias de rowid: chega-se ao blob por seek direto, sem índice
        -- secundário. A busca só lê as poucas ruas que sobraram do ranqueamento, então
        -- deixar o blob fora da tabela logradouro é o que impede a varredura de um
        -- município inteiro de arrastar a numeração junto.
        CREATE TABLE numeracao (
            log_id INTEGER PRIMARY KEY,
            n INTEGER NOT NULL,
            dados BLOB NOT NULL
        );
        CREATE TABLE tipo_logradouro (id INTEGER PRIMARY KEY, nome TEXT);
    """)
    return con


def _pontas(lg: AgregadoLog, lat: float, lon: float, raio_m: float):
    """Ponta que caiu longe do corpo da rua é número de casa errado no cadastro;
    interpolar por ela mandaria a casa procurada para outro bairro. Como a faixa só
    vale inteira, uma ponta ruim descarta as duas e sobra o centroide."""
    cos = math.cos(math.radians(lat))
    limite = max(1.5 * raio_m, 500.0)

    def perto(p) -> bool:
        return p is not None and math.hypot((p[0] - lat) * GRAU_EM_METROS,
                                            (p[1] - lon) * GRAU_EM_METROS * cos) <= limite

    if not (perto(lg.ponta_min) and perto(lg.ponta_max)):
        return None, None, (lat, lon), (lat, lon)
    return lg.num_min, lg.num_max, lg.ponta_min, lg.ponta_max


def gravar_logradouros(con: sqlite3.Connection, logs: dict[tuple, AgregadoLog],
                       proximo_id: int) -> tuple[int, int, int]:
    """Chamado ao fim de cada UF: um município pertence a uma só UF, então a chave
    nunca cruza arquivos e o acumulador pode ser esvaziado aqui.

    Devolve (logradouros gravados, próximo id livre, casas numeradas).
    """
    linhas = []
    numeros = []
    n_pares = 0
    for (cod, via, tipo), lg in logs.items():
        lat, lon = lg.centroide()
        lat_e6, lon_e6 = round(lat * 1e6), round(lon * 1e6)
        raio = min(RAIO_MAX_M, max(RAIO_MIN_M, lg.raio_bruto_m()))
        num_min, num_max, p_min, p_max = _pontas(lg, lat, lon, raio)
        log_id = proximo_id
        proximo_id += 1
        linhas.append((
            int(cod), via, tipo, lg.n,
            int(lg.cep.valor) if lg.cep.valor else None,
            lat_e6, lon_e6, round(raio),
            num_min, num_max,
            # Pontas como deslocamento do centroide: cabem em 2 ou 3 bytes de varint,
            # contra 4 se fossem coordenadas absolutas.
            round((p_min[0] - lat) * 1e6), round((p_min[1] - lon) * 1e6),
            round((p_max[0] - lat) * 1e6), round((p_max[1] - lon) * 1e6),
            log_id,
        ))
        if lg.nums is not None:
            # A âncora tem de ser o inteiro que foi para a linha acima, não o float de
            # onde ele saiu: meio micrograu de diferença aqui desloca a rua inteira na
            # leitura, e em silêncio.
            n, blob = codificar_numeracao(lg.nums, lat_e6, lon_e6)
            numeros.append((log_id, n, blob))
            n_pares += n
    con.executemany(
        "INSERT OR REPLACE INTO logradouro VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", linhas)
    con.executemany("INSERT OR REPLACE INTO numeracao VALUES (?,?,?)", numeros)
    con.commit()
    return len(linhas), proximo_id, n_pares


def gravar(con: sqlite3.Connection, dados: dict[str, Agregado],
           tipos: dict[str, int], n_logradouros: int, n_numeros: int) -> None:
    por_municipio: dict[str, list[float]] = {}
    linhas = []
    for cep, ag in dados.items():
        lat, lon = ag.centroide()
        cod = ag.municipio.valor
        bruto = ag.raio_bruto_m()
        # CEP único de cidade pequena espalha por todo o município: serve para conferir
        # o município, nunca para conferir a distância até o ponto devolvido.
        linhas.append((cep, round(lat * 1e6), round(lon * 1e6),
                       round(min(RAIO_MAX_M, max(RAIO_MIN_M, bruto))),
                       int(bruto > RAIO_MAX_M), ag.n,
                       ag.logradouro.valor or None, ag.localidade.valor or None,
                       cod or None))
        if cod:
            acc = por_municipio.setdefault(cod, [0.0, 0.0, 0.0, 0.0, 0.0])
            acc[0] += 1
            acc[1] += lat
            acc[2] += lon
            acc[3] += lat * lat
            acc[4] += lon * lon
    con.executemany("INSERT OR REPLACE INTO cep VALUES (?,?,?,?,?,?,?,?,?)", linhas)

    nomes = nomes_de_municipio()
    munis = []
    for cod, (n, slat, slon, slat2, slon2) in por_municipio.items():
        lat, lon = slat / n, slon / n
        if n >= 2:
            dp_lat = math.sqrt(max(0.0, slat2 / n - lat * lat)) * GRAU_EM_METROS
            dp_lon = (math.sqrt(max(0.0, slon2 / n - lon * lon)) * GRAU_EM_METROS
                      * math.cos(math.radians(lat)))
            # Teto para não virar filtro inútil: municípios amazônicos chegam a 280 km
            # de dispersão, o que alcançaria as cidades vizinhas.
            raio = min(80_000.0, max(2000.0, 2.0 * math.hypot(dp_lat, dp_lon)))
        else:
            raio = 5000.0
        nome, uf = nomes.get(cod, (None, None))
        munis.append((cod, nome, uf, round(lat * 1e6), round(lon * 1e6), round(raio),
                      int(n), 0))
    con.executemany("INSERT OR REPLACE INTO municipio VALUES (?,?,?,?,?,?,?,?)", munis)
    # Quantas ruas o município tem decide se vale montar o índice invertido dele na RAM
    # quando a busca varre a vizinhança do foco. Sai por consulta à tabela em vez de
    # contador acumulado porque o mesmo município pode ser gravado em vários passes.
    con.execute("""
        UPDATE municipio SET n_log = COALESCE(
            (SELECT COUNT(*) FROM logradouro
              WHERE logradouro.cod_ibge = CAST(municipio.cod_ibge AS INTEGER)), 0)
    """)
    con.executemany("INSERT OR REPLACE INTO tipo_logradouro VALUES (?,?)",
                    [(i, nome) for nome, i in tipos.items()])

    con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [
        ("fonte", "IBGE CNEFE Censo 2022"),
        ("gerado_em", time.strftime("%Y-%m-%d")),
        ("n_ceps", str(len(linhas))),
        ("n_municipios", str(len(munis))),
        ("n_logradouros", str(n_logradouros)),
        ("n_numeros", str(n_numeros)),
        # O backend recusa a busca por rua se não achar esta chave: uma base gerada
        # antes do índice tem as tabelas do CEP idênticas e passaria despercebida.
        # 2 acrescenta a tabela numeracao; o backend compara como inteiro, então uma
        # base 1 ainda serve, só posiciona a casa por interpolação entre as pontas.
        ("versao_indice", "2"),
    ])
    con.execute("CREATE INDEX idx_cep_municipio ON cep(cod_ibge)")
    con.commit()


def finalizar(con: sqlite3.Connection, tmp: Path, destino: Path) -> None:
    con.execute("VACUUM")
    con.close()
    destino.unlink(missing_ok=True)
    tmp.replace(destino)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parents[1] / "backend" / "vendor" / "cnefe.sqlite")
    ap.add_argument("--cache", type=Path, default=None,
                    help="diretório para guardar os zips baixados (permite reprocessar sem rebaixar)")
    ap.add_argument("--ufs", nargs="*", default=UFS)
    ap.add_argument("--num-passes", type=int, default=1,
                    help="relê cada CSV N vezes, tratando 1/N dos municípios por vez. "
                         "Só serve para máquina apertada de RAM: São Paulo sozinho "
                         "segura ~280 MB de numeração até o fim da UF, e 3 passes "
                         "derrubam isso para ~95 MB ao custo de reler o arquivo.")
    args = ap.parse_args()

    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    livre = shutil.disk_usage(args.out.parent).free
    # A base sai em ~440 MB e o VACUUM final escreve uma segunda cópia antes de trocar.
    if len(args.ufs) > 20 and livre < 1_100_000_000:
        raise SystemExit(f"espaço insuficiente em {args.out.parent}: "
                         f"{livre / 1e9:.1f} GB livres, preciso de ~1,1 GB")

    dados: dict[str, Agregado] = {}
    tipos: dict[str, int] = {}
    n_logradouros = 0
    n_numeros = 0
    proximo_id = 1
    tmp = args.out.with_suffix(".tmp")
    con = criar_base(tmp)
    inicio = time.time()
    for i, uf in enumerate(args.ufs, 1):
        t = time.time()
        linhas = 0
        for passe in range(args.num_passes):
            # Os logradouros são descarregados a cada UF; só os CEPs atravessam o laço,
            # porque um mesmo CEP genérico pode aparecer em mais de um estado.
            logs: dict[tuple, AgregadoLog] = {}
            linhas = processar_uf(uf, dados, logs, tipos, args.cache,
                                  passe, args.num_passes)
            n, proximo_id, pares = gravar_logradouros(con, logs, proximo_id)
            n_logradouros += n
            n_numeros += pares
        print(f"[{i}/{len(args.ufs)}] {uf}: {linhas:>10,} linhas  "
              f"{time.time() - t:6.1f}s  acumulado {len(dados):,} CEPs, "
              f"{n_logradouros:,} logradouros, {n_numeros:,} casas", flush=True)

    if not dados:
        raise SystemExit("nenhum CEP agregado — verifique a fonte")
    gravar(con, dados, tipos, n_logradouros, n_numeros)
    finalizar(con, tmp, args.out)
    mb = args.out.stat().st_size / 1e6
    print(f"OK {args.out} — {len(dados):,} CEPs, {n_logradouros:,} logradouros, "
          f"{n_numeros:,} casas numeradas, {mb:.1f} MB, "
          f"{time.time() - inicio:.0f}s no total")


if __name__ == "__main__":
    sys.exit(main())
