"""Gera cnefe.sqlite a partir dos microdados do CNEFE/Censo 2022 do IBGE.

Duas agregações do mesmo passeio pelos CSVs:

- por CEP, guardando centroide, raio e o logradouro/localidade/município predominantes;
- por (município, logradouro), que é o que permite responder "esta rua existe?" antes
  de propor um endereço ao usuário. Sem ela só dava para validar quem trouxesse CEP —
  e 4.490 dos 5.570 municípios têm menos de cinco CEPs na base.

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
import sqlite3
import sys
import time
import urllib.request
import zipfile
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
           "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR", "NUM_ENDERECO", "LATITUDE", "LONGITUDE")

RAIO_MIN_M = 250.0
RAIO_MAX_M = 5000.0
GRAU_EM_METROS = 111320.0


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
    número encontrados, para interpolar a posição da casa procurada — o centroide
    sozinho erra por quilômetros numa avenida longa."""

    __slots__ = ("cep", "num_min", "num_max", "ponta_min", "ponta_max")

    def __init__(self) -> None:
        super().__init__()
        self.cep = Maioria()
        self.num_min: int | None = None
        self.num_max: int | None = None
        self.ponta_min: tuple[float, float] | None = None
        self.ponta_max: tuple[float, float] | None = None

    def numerar(self, numero: int, lat: float, lon: float) -> None:
        if self.num_min is None or numero < self.num_min:
            self.num_min, self.ponta_min = numero, (lat, lon)
        if self.num_max is None or numero > self.num_max:
            self.num_max, self.ponta_max = numero, (lat, lon)


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


def processar_uf(nome: str, dados: dict[str, Agregado],
                 logs: dict[tuple, AgregadoLog], tipos: dict[str, int],
                 cache: Path | None) -> int:
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
        i_cep, i_mun, i_loc, i_tipo, i_titulo, i_nome, i_num, i_lat, i_lon = idx

        for row in leitor:
            linhas += 1
            try:
                lat = float(row[i_lat])
                lon = float(row[i_lon])
            except (IndexError, ValueError):
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
            lat INTEGER, lon INTEGER, raio_m INTEGER, n_ceps INTEGER
        );
        CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT);
        -- Sem rowid: a chave primária já ordena a tabela por município, que é como
        -- toda consulta chega. Um índice à parte custaria 25 B por linha, 55 MB no
        -- Brasil, para repetir o que a tabela já faz.
        CREATE TABLE logradouro (
            cod_ibge INTEGER, nome TEXT, tipo INTEGER,
            n_end INTEGER, cep INTEGER, lat INTEGER, lon INTEGER, raio_m INTEGER,
            num_min INTEGER, num_max INTEGER,
            dlat_min INTEGER, dlon_min INTEGER, dlat_max INTEGER, dlon_max INTEGER,
            PRIMARY KEY (cod_ibge, nome, tipo)
        ) WITHOUT ROWID;
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


def gravar_logradouros(con: sqlite3.Connection, logs: dict[tuple, AgregadoLog]) -> int:
    """Chamado ao fim de cada UF: um município pertence a uma só UF, então a chave
    nunca cruza arquivos e o acumulador pode ser esvaziado aqui."""
    linhas = []
    for (cod, via, tipo), lg in logs.items():
        lat, lon = lg.centroide()
        raio = min(RAIO_MAX_M, max(RAIO_MIN_M, lg.raio_bruto_m()))
        num_min, num_max, p_min, p_max = _pontas(lg, lat, lon, raio)
        linhas.append((
            int(cod), via, tipo, lg.n,
            int(lg.cep.valor) if lg.cep.valor else None,
            round(lat * 1e6), round(lon * 1e6), round(raio),
            num_min, num_max,
            # Pontas como deslocamento do centroide: cabem em 2 ou 3 bytes de varint,
            # contra 4 se fossem coordenadas absolutas.
            round((p_min[0] - lat) * 1e6), round((p_min[1] - lon) * 1e6),
            round((p_max[0] - lat) * 1e6), round((p_max[1] - lon) * 1e6),
        ))
    con.executemany(
        "INSERT OR REPLACE INTO logradouro VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", linhas)
    con.commit()
    return len(linhas)


def gravar(con: sqlite3.Connection, dados: dict[str, Agregado],
           tipos: dict[str, int], n_logradouros: int) -> None:
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
        munis.append((cod, nome, uf, round(lat * 1e6), round(lon * 1e6), round(raio), int(n)))
    con.executemany("INSERT OR REPLACE INTO municipio VALUES (?,?,?,?,?,?,?)", munis)
    con.executemany("INSERT OR REPLACE INTO tipo_logradouro VALUES (?,?)",
                    [(i, nome) for nome, i in tipos.items()])

    con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [
        ("fonte", "IBGE CNEFE Censo 2022"),
        ("gerado_em", time.strftime("%Y-%m-%d")),
        ("n_ceps", str(len(linhas))),
        ("n_municipios", str(len(munis))),
        ("n_logradouros", str(n_logradouros)),
        # O backend recusa a busca por rua se não achar esta chave: uma base gerada
        # antes do índice tem as tabelas do CEP idênticas e passaria despercebida.
        ("versao_indice", "1"),
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
    args = ap.parse_args()

    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    dados: dict[str, Agregado] = {}
    tipos: dict[str, int] = {}
    n_logradouros = 0
    tmp = args.out.with_suffix(".tmp")
    con = criar_base(tmp)
    inicio = time.time()
    for i, uf in enumerate(args.ufs, 1):
        t = time.time()
        # Os logradouros são descarregados a cada UF; só os CEPs atravessam o laço,
        # porque um mesmo CEP genérico pode aparecer em mais de um estado.
        logs: dict[tuple, AgregadoLog] = {}
        n = processar_uf(uf, dados, logs, tipos, args.cache)
        n_logradouros += gravar_logradouros(con, logs)
        print(f"[{i}/{len(args.ufs)}] {uf}: {n:>10,} linhas  "
              f"{time.time() - t:6.1f}s  acumulado {len(dados):,} CEPs, "
              f"{n_logradouros:,} logradouros", flush=True)

    if not dados:
        raise SystemExit("nenhum CEP agregado — verifique a fonte")
    gravar(con, dados, tipos, n_logradouros)
    finalizar(con, tmp, args.out)
    mb = args.out.stat().st_size / 1e6
    print(f"OK {args.out} — {len(dados):,} CEPs, {n_logradouros:,} logradouros, "
          f"{mb:.1f} MB, {time.time() - inicio:.0f}s no total")


if __name__ == "__main__":
    sys.exit(main())
