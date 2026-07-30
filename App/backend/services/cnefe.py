"""Consulta à base local do CNEFE/IBGE: CEP -> centroide, raio e município.

A base é opcional. Sem ela o app continua funcionando — a validação de endereço
apenas perde a âncora geográfica e passa a depender só do ViaCEP.
"""

import math
import sqlite3
import threading

from core.paths import cnefe_db
from core.schemas import CnefeCep, CnefeMunicipio, CnefeStatus

_local = threading.local()

_CAMPOS_CEP = ("cep", "lat", "lon", "raio_m", "generico", "n_enderecos",
               "logradouro", "localidade", "cod_ibge")


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


def status() -> CnefeStatus:
    con = _conexao()
    if con is None:
        return CnefeStatus(disponivel=False)
    meta = {k: v for k, v in con.execute("SELECT chave, valor FROM meta")}
    return CnefeStatus(
        disponivel=True,
        fonte=meta.get("fonte"),
        gerado_em=meta.get("gerado_em"),
        n_ceps=int(meta.get("n_ceps", 0)),
        n_municipios=int(meta.get("n_municipios", 0)),
        caminho=str(cnefe_db()),
    )


def distancia_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 6_371_000 * 2 * math.asin(math.sqrt(a))
