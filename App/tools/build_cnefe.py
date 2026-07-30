"""Gera cnefe.sqlite a partir dos microdados do CNEFE/Censo 2022 do IBGE.

Agrega ~220 milhões de endereços em ~1,2 milhão de CEPs, guardando centroide, raio
e o logradouro/localidade/município predominantes. Uso:

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

FTP = ("https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos"
       "/Censo_Demografico_2022/Arquivos_CNEFE/CSV/UF/")
MUNICIPIOS_API = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"

UFS = [
    "11_RO", "12_AC", "13_AM", "14_RR", "15_PA", "16_AP", "17_TO", "21_MA", "22_PI",
    "23_CE", "24_RN", "25_PB", "26_PE", "27_AL", "28_SE", "29_BA", "31_MG", "32_ES",
    "33_RJ", "35_SP", "41_PR", "42_SC", "43_RS", "50_MS", "51_MT", "52_GO", "53_DF",
]

COLUNAS = ("CEP", "COD_MUNICIPIO", "DSC_LOCALIDADE", "NOM_TIPO_SEGLOGR",
           "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR", "LATITUDE", "LONGITUDE")

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


class Agregado:
    __slots__ = ("n", "slat", "slon", "slat2", "slon2", "logradouro", "localidade", "municipio")

    def __init__(self) -> None:
        self.n = 0
        self.slat = self.slon = self.slat2 = self.slon2 = 0.0
        self.logradouro = Maioria()
        self.localidade = Maioria()
        self.municipio = Maioria()

    def add(self, lat: float, lon: float) -> None:
        self.n += 1
        self.slat += lat
        self.slon += lon
        self.slat2 += lat * lat
        self.slon2 += lon * lon

    def centroide(self) -> tuple[float, float]:
        return self.slat / self.n, self.slon / self.n

    def raio_bruto_m(self) -> float:
        """2 desvios-padrão da nuvem de endereços do CEP. Cobre a rua inteira sem
        inflar com o outlier de digitação que todo cadastro tem."""
        if self.n < 2:
            return RAIO_MIN_M
        lat, lon = self.centroide()
        var_lat = max(0.0, self.slat2 / self.n - lat * lat)
        var_lon = max(0.0, self.slon2 / self.n - lon * lon)
        dp_lat = math.sqrt(var_lat) * GRAU_EM_METROS
        dp_lon = math.sqrt(var_lon) * GRAU_EM_METROS * math.cos(math.radians(lat))
        return 2.0 * math.hypot(dp_lat, dp_lon)


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


def processar_uf(nome: str, dados: dict[str, Agregado], cache: Path | None) -> int:
    z, texto = _abrir_csv(nome, cache)
    linhas = 0
    try:
        leitor = csv.reader(texto, delimiter=";")
        cabecalho = next(leitor)
        try:
            idx = [cabecalho.index(c) for c in COLUNAS]
        except ValueError:
            raise SystemExit(f"{nome}: colunas esperadas ausentes. Lido: {cabecalho}")
        i_cep, i_mun, i_loc, i_tipo, i_titulo, i_nome, i_lat, i_lon = idx

        for row in leitor:
            linhas += 1
            try:
                cep = row[i_cep]
                if len(cep) != 8 or not cep.isdigit():
                    continue
                lat = float(row[i_lat])
                lon = float(row[i_lon])
            except (IndexError, ValueError):
                continue
            ag = dados.get(cep)
            if ag is None:
                ag = dados[cep] = Agregado()
            ag.add(lat, lon)
            ag.municipio.add(row[i_mun])
            ag.localidade.add(row[i_loc])
            ag.logradouro.add(_juntar_logradouro(row[i_tipo], row[i_titulo], row[i_nome]))
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


def gravar(dados: dict[str, Agregado], destino: Path) -> None:
    tmp = destino.with_suffix(".tmp")
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
    """)

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

    con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [
        ("fonte", "IBGE CNEFE Censo 2022"),
        ("gerado_em", time.strftime("%Y-%m-%d")),
        ("n_ceps", str(len(linhas))),
        ("n_municipios", str(len(munis))),
    ])
    con.execute("CREATE INDEX idx_cep_municipio ON cep(cod_ibge)")
    con.commit()
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
    inicio = time.time()
    for i, uf in enumerate(args.ufs, 1):
        t = time.time()
        n = processar_uf(uf, dados, args.cache)
        print(f"[{i}/{len(args.ufs)}] {uf}: {n:>10,} linhas  "
              f"{time.time() - t:6.1f}s  acumulado {len(dados):,} CEPs", flush=True)

    if not dados:
        raise SystemExit("nenhum CEP agregado — verifique a fonte")
    gravar(dados, args.out)
    mb = args.out.stat().st_size / 1e6
    print(f"OK {args.out} — {len(dados):,} CEPs, {mb:.1f} MB, "
          f"{time.time() - inicio:.0f}s no total")


if __name__ == "__main__":
    sys.exit(main())
