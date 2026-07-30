"""Mede a geocodificação contra um gabarito, antes e depois da validação.

Sem número, "melhorou a geocodificação" é opinião. O gabarito sai do próprio CNEFE:
cada CEP da base tem logradouro, bairro, município e a coordenada apurada pelo IBGE.

Por padrão o texto **não** inclui o CEP: incluí-lo daria ao caminho novo a âncora de
graça e mediria o CNEFE contra ele mesmo. Sem CEP, a referência do IBGE é independente
das duas respostas e a comparação de município é honesta. `--com-cep` reproduz o romaneio
real, onde o CEP costuma estar presente — vale para ler a distribuição de status, não a
distância.

    python tools/eval_addresses.py --amostra 25
    python tools/eval_addresses.py --amostra 25 --com-cep
    python tools/eval_addresses.py --gabarito meus_enderecos.csv   # texto;municipio
"""

import argparse
import csv
import random
import sqlite3
import statistics
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from core.config import load_config  # noqa: E402
from core.paths import cnefe_db  # noqa: E402
from services import address_resolver, cnefe, ors_client  # noqa: E402
from services import br_address_terms as termos  # noqa: E402
from services.ors_client import OrsError  # noqa: E402

LIMITE_MUNICIPIO_KM = 15.0


def amostrar(n: int, seed: int, com_cep: bool) -> list[dict]:
    caminho = cnefe_db()
    if not caminho:
        raise SystemExit("Base do CNEFE ausente. Rode tools/build_cnefe.py primeiro.")
    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    total = con.execute("select max(rowid) from cep").fetchone()[0]
    rnd = random.Random(seed)
    linhas: list[dict] = []
    vistos: set[int] = set()
    while len(linhas) < n:
        rowid = rnd.randint(1, total)
        if rowid in vistos:
            continue
        vistos.add(rowid)
        r = con.execute(
            "select c.cep, c.logradouro, c.localidade, c.lat, c.lon, m.nome, m.uf"
            "  from cep c join municipio m on m.cod_ibge = c.cod_ibge"
            " where c.rowid = ? and c.generico = 0 and c.logradouro is not null",
            (rowid,),
        ).fetchone()
        if not r:
            continue
        cep, logradouro, bairro, lat, lon, municipio, uf = r
        partes = [logradouro.title(), (bairro or "").title(), f"{municipio} - {uf}"]
        if com_cep:
            partes.append(f"{cep[:5]}-{cep[5:]}")
        linhas.append({
            "texto": ", ".join(p for p in partes if p),
            "municipio": municipio,
            "lat": lat / 1e6,
            "lon": lon / 1e6,
        })
    con.close()
    return linhas


def ler_gabarito(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        return [
            {"texto": linha[0].strip(), "municipio": linha[1].strip(),
             "lat": float(linha[2]) if len(linha) > 2 else None,
             "lon": float(linha[3]) if len(linha) > 3 else None}
            for linha in csv.reader(f, delimiter=";") if len(linha) >= 2
        ]


def _municipio_bate(nomes: list[str | None], esperado: str) -> bool:
    alvo = termos.normalizar(esperado)
    return any(SequenceMatcher(None, termos.normalizar(n), alvo).ratio() >= 0.85
               for n in nomes if n)


def avaliar(caso: dict, lat, lon, nomes: list[str | None]) -> tuple[bool, float | None]:
    erro = None
    if lat is not None and caso["lat"] is not None:
        erro = cnefe.distancia_m(lat, lon, caso["lat"], caso["lon"]) / 1000
    if nomes and any(nomes):
        return _municipio_bate(nomes, caso["municipio"]), erro
    return (erro is not None and erro <= LIMITE_MUNICIPIO_KM), erro


def antigo(texto: str, key: str) -> tuple:
    """O comportamento anterior: texto cru no geocoder e o primeiro palpite aceito."""
    try:
        hits = ors_client.geocode_search(key, texto)
    except OrsError:
        return None, None, []
    if not hits:
        return None, None, []
    h = hits[0]
    return h.lat, h.lon, [h.locality, h.localadmin, h.county]


def resumir(nome: str, acertos: list[bool], erros: list[float]) -> None:
    n = len(acertos)
    certo = sum(acertos)
    print(f"\n{nome}")
    print(f"  municipio correto : {certo}/{n} ({100 * certo / n:.0f}%)")
    print(f"  municipio ERRADO  : {n - certo}/{n} ({100 * (n - certo) / n:.0f}%)")
    if erros:
        print(f"  erro mediano      : {statistics.median(erros):.2f} km"
              f"  (p90 {statistics.quantiles(erros, n=10)[8]:.2f} km)" if len(erros) > 1
              else f"  erro mediano      : {erros[0]:.2f} km")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--amostra", type=int, default=25)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--gabarito", type=Path)
    ap.add_argument("--com-cep", action="store_true",
                    help="inclui o CEP no texto, como num romaneio real")
    args = ap.parse_args()

    key = load_config().ors_api_key
    if not key:
        raise SystemExit("Configure a chave do OpenRouteService antes de avaliar.")

    casos = (ler_gabarito(args.gabarito) if args.gabarito
             else amostrar(args.amostra, args.seed, args.com_cep))
    print(f"{len(casos)} endereços | base CNEFE: {cnefe.disponivel()}")

    status: dict[str, int] = {}
    ok_novo, ok_velho, erro_novo, erro_velho = [], [], [], []
    for i, caso in enumerate(casos, 1):
        r = address_resolver.resolve(caso["texto"], api_key=key)
        status[r.status] = status.get(r.status, 0) + 1
        nomes = [r.hit.locality, r.hit.localadmin, r.hit.county] if r.hit else []
        certo, erro = avaliar(caso, r.lat, r.lon, nomes)
        ok_novo.append(certo)
        if erro is not None:
            erro_novo.append(erro)

        lat, lon, nomes_v = antigo(caso["texto"], key)
        certo_v, erro_v = avaliar(caso, lat, lon, nomes_v)
        ok_velho.append(certo_v)
        if erro_v is not None:
            erro_velho.append(erro_v)

        marca = "  " if certo else "!!"
        print(f"{marca} [{i:>3}] {r.status:<14} {caso['municipio'][:22]:<22} {caso['texto'][:58]}")

    resumir("ANTES (texto cru, primeiro palpite)", ok_velho, erro_velho)
    resumir("DEPOIS (cascata validada)", ok_novo, erro_novo)
    print("\nstatus:", ", ".join(f"{k}={v}" for k, v in sorted(status.items())))


if __name__ == "__main__":
    main()
