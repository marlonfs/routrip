"""Consulta de CEP com cache local, throttle e circuit breaker.

O ViaCEP proíbe explicitamente "uso massivo para validação de bases locais" sob pena
de bloqueio. Uma importação de romaneio pode ter dezenas de CEPs, então o cache e o
espaçamento entre chamadas não são otimização: são o que mantém o acesso vivo.
"""

import sqlite3
import threading
import time

import httpx

from core.paths import app_data_dir
from core.schemas import CepInfo

VIACEP = "https://viacep.com.br/ws/{cep}/json/"
BRASILAPI = "https://brasilapi.com.br/api/cep/v2/{cep}"

TIMEOUT = httpx.Timeout(6.0, connect=4.0)
INTERVALO_MIN_S = 0.2
TTL_ACERTO_S = 90 * 24 * 3600
TTL_INEXISTENTE_S = 7 * 24 * 3600
FALHAS_PARA_ABRIR = 3
PAUSA_CIRCUITO_S = 300
# Folgado para o uso interativo (uma importação grande são dezenas de CEPs, e repetições
# saem do cache), apertado o bastante para que um laço acidental não gaste o dia inteiro
# de acesso antes de alguém perceber.
TETO_POR_HORA = 300
JANELA_S = 3600

_lock = threading.Lock()
_ultima_chamada = 0.0
_falhas_seguidas = 0
_circuito_aberto_ate = 0.0
_janela_inicio = 0.0
_consultas_na_janela = 0
_local = threading.local()


class CepIndisponivel(Exception):
    """A consulta remota falhou e não havia cache — diferente de CEP inexistente."""


def _cache() -> sqlite3.Connection:
    con = getattr(_local, "con", None)
    if con is None:
        con = sqlite3.connect(app_data_dir() / "cache.db", check_same_thread=False)
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("""CREATE TABLE IF NOT EXISTS cep (
            cep TEXT PRIMARY KEY, payload TEXT, existe INTEGER, ts REAL)""")
        con.commit()
        _local.con = con
    return con


def _ler_cache(cep: str) -> tuple[bool, CepInfo | None] | None:
    row = _cache().execute("SELECT payload, existe, ts FROM cep WHERE cep = ?", (cep,)).fetchone()
    if row is None:
        return None
    payload, existe, ts = row
    ttl = TTL_ACERTO_S if existe else TTL_INEXISTENTE_S
    if time.time() - ts > ttl:
        return None
    return (True, CepInfo.model_validate_json(payload)) if existe else (False, None)


def _gravar_cache(cep: str, info: CepInfo | None) -> None:
    con = _cache()
    con.execute("INSERT OR REPLACE INTO cep VALUES (?,?,?,?)",
                (cep, info.model_dump_json() if info else "", int(info is not None), time.time()))
    con.commit()


def _throttle() -> None:
    global _ultima_chamada
    with _lock:
        espera = INTERVALO_MIN_S - (time.monotonic() - _ultima_chamada)
        if espera > 0:
            time.sleep(espera)
        _ultima_chamada = time.monotonic()


def _registrar(sucesso: bool) -> None:
    global _falhas_seguidas, _circuito_aberto_ate
    with _lock:
        if sucesso:
            _falhas_seguidas = 0
            return
        _falhas_seguidas += 1
        if _falhas_seguidas >= FALHAS_PARA_ABRIR:
            _circuito_aberto_ate = time.monotonic() + PAUSA_CIRCUITO_S


def _circuito_fechado() -> bool:
    with _lock:
        return time.monotonic() >= _circuito_aberto_ate


def _dentro_do_teto() -> bool:
    global _janela_inicio, _consultas_na_janela
    with _lock:
        agora = time.monotonic()
        if agora - _janela_inicio >= JANELA_S:
            _janela_inicio, _consultas_na_janela = agora, 0
        if _consultas_na_janela >= TETO_POR_HORA:
            return False
        _consultas_na_janela += 1
        return True


def _erro_viacep(dados: dict) -> bool:
    # CEP inexistente volta 200 com {"erro": true}, e já apareceu como string "true".
    return str(dados.get("erro", "")).lower() == "true"


def _do_viacep(cep: str, client: httpx.Client) -> CepInfo | None:
    resp = client.get(VIACEP.format(cep=cep))
    resp.raise_for_status()
    dados = resp.json()
    if _erro_viacep(dados):
        return None
    return CepInfo(
        cep=cep,
        logradouro=dados.get("logradouro") or None,
        bairro=dados.get("bairro") or None,
        localidade=dados.get("localidade") or None,
        uf=dados.get("uf") or None,
        ibge=dados.get("ibge") or None,
        generico=not (dados.get("logradouro") or "").strip(),
        source="viacep",
    )


def _do_brasilapi(cep: str, client: httpx.Client) -> CepInfo | None:
    resp = client.get(BRASILAPI.format(cep=cep))
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    dados = resp.json()
    return CepInfo(
        cep=cep,
        logradouro=dados.get("street") or None,
        bairro=dados.get("neighborhood") or None,
        localidade=dados.get("city") or None,
        uf=dados.get("state") or None,
        generico=not (dados.get("street") or "").strip(),
        source="brasilapi",
    )


def consultar(cep: str) -> CepInfo | None:
    """Devolve None quando o CEP não existe. Levanta CepIndisponivel quando não foi
    possível saber — o chamador precisa distinguir "não existe" de "não consegui ver"."""
    limpo = "".join(c for c in cep if c.isdigit())
    if len(limpo) != 8:
        return None

    em_cache = _ler_cache(limpo)
    if em_cache is not None:
        return em_cache[1]

    if not _circuito_fechado():
        raise CepIndisponivel("consulta de CEP temporariamente suspensa")

    if not _dentro_do_teto():
        raise CepIndisponivel("limite de consultas de CEP por hora atingido")

    _throttle()
    erro: Exception | None = None
    with httpx.Client(timeout=TIMEOUT) as client:
        for provedor in (_do_viacep, _do_brasilapi):
            try:
                info = provedor(limpo, client)
            except (httpx.HTTPError, ValueError) as exc:
                erro = exc
                continue
            _registrar(True)
            _gravar_cache(limpo, info)
            return info

    _registrar(False)
    raise CepIndisponivel(str(erro) if erro else "falha ao consultar CEP")
