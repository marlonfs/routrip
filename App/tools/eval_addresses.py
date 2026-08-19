"""Mede a geocodificação contra um gabarito, antes e depois da validação.

Sem número, "melhorou a geocodificação" é opinião. Há duas origens de gabarito:

- `--fonte-csv`: sorteia **linhas individuais** dos zips do CNEFE, cada uma com a
  coordenada daquela casa. É o gabarito honesto para medir a base, porque a linha crua
  não passou pela agregação que o índice de logradouros faz — comparar o índice com a
  tabela `cep` da mesma base seria autorreferente.
- padrão: sorteia CEPs da base. Serve para medir o ORS, não o CNEFE.

Por padrão o texto **não** inclui o CEP: incluí-lo daria ao caminho novo a âncora de
graça. `--com-cep` reproduz o romaneio real, onde o CEP costuma estar presente — vale
para ler a distribuição de status, não a distância.

**Ressalva que muda a leitura do número:** `--fonte-csv` sorteia linhas do próprio
microdado, então o número procurado existe no cadastro por construção. O que ele mede,
numa base v2, é o caso `exato` — o piso do erro. O caso que interessa medir de verdade é
o número **ausente** do cadastro, e para isso existe `--modo-numeracao`, que faz
leave-one-out sobre a tabela `numeracao`: esconde um número e manda a base deduzi-lo
pelos dois vizinhos, exatamente como `cnefe.posicionar` faz em produção.

    python tools/eval_addresses.py --fonte-csv ../.cache-cnefe --amostra 300 --sem-rede
    python tools/eval_addresses.py --fonte-csv ../.cache-cnefe --amostra 300
    python tools/eval_addresses.py --gabarito meus_enderecos.csv   # texto;municipio
    python tools/eval_addresses.py --modo-numeracao --amostra 20000
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

from build_cnefe import COLUNAS, UFS, _abrir_csv, _juntar_logradouro, _numero  # noqa: E402
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


def _texto_do_caso(rua: str, numero: int, bairro: str, muni, cep: str,
                   com_cep: bool) -> str:
    partes = [rua.title(), str(numero), bairro.title(), f"{muni.nome} - {muni.uf}"]
    if com_cep and cep:
        partes.append(f"{cep[:5]}-{cep[5:]}")
    return ", ".join(p for p in partes if p)


def amostrar_csv(n: int, seed: int, cache: Path, ufs: list[str], com_cep: bool) -> list[dict]:
    """Sorteia endereços das linhas cruas do microdado, com a coordenada da casa.

    Reservatório em vez de sorteio por posição: o zip é um fluxo comprimido, não dá para
    pular para a linha 8.412.905 sem descomprimir tudo o que vem antes. Parar na metade
    também não serve — o CSV vem em ordem de setor censitário, e a amostra ficaria presa
    aos primeiros municípios do arquivo.
    """
    rnd = random.Random(seed)
    por_uf = max(1, n // len(ufs))
    casos: list[dict] = []
    for uf in ufs:
        z, texto = _abrir_csv(uf, cache)
        reservatorio: list[tuple] = []
        vistas = 0
        try:
            leitor = csv.reader(texto, delimiter=";")
            cabecalho = next(leitor)
            try:
                # Por nome, não por posição: `COLUNAS` cresce quando o build passa a ler
                # mais do microdado, e um desempacotamento posicional quebra junto.
                idx = {c: cabecalho.index(c) for c in COLUNAS}
            except ValueError:
                raise SystemExit(f"{uf}: colunas esperadas ausentes. Lido: {cabecalho}")
            i_cep, i_mun, i_loc = idx["CEP"], idx["COD_MUNICIPIO"], idx["DSC_LOCALIDADE"]
            i_tipo, i_titulo = idx["NOM_TIPO_SEGLOGR"], idx["NOM_TITULO_SEGLOGR"]
            i_nome, i_num = idx["NOM_SEGLOGR"], idx["NUM_ENDERECO"]
            i_lat, i_lon = idx["LATITUDE"], idx["LONGITUDE"]
            for row in leitor:
                # Sem número não há casa para comparar; o que sobraria é o logradouro,
                # que é justamente o que o índice agrega — gabarito do próprio índice.
                num = _numero(row[i_num])
                if num is None or not row[i_nome].strip():
                    continue
                try:
                    lat, lon = float(row[i_lat]), float(row[i_lon])
                except (IndexError, ValueError):
                    continue
                vistas += 1
                item = (_juntar_logradouro(row[i_tipo], row[i_titulo], row[i_nome]),
                        num, row[i_loc], row[i_mun], row[i_cep], lat, lon)
                if len(reservatorio) < por_uf:
                    reservatorio.append(item)
                else:
                    j = rnd.randrange(vistas)
                    if j < por_uf:
                        reservatorio[j] = item
        finally:
            texto.close()
            z.close()

        for rua, num, bairro, cod, cep, lat, lon in reservatorio:
            muni = cnefe.lookup_municipio(cod)
            if muni is None or not muni.nome:
                continue
            casos.append({
                "texto": _texto_do_caso(rua, num, bairro, muni,
                                        cep if len(cep) == 8 and cep.isdigit() else "",
                                        com_cep),
                "municipio": muni.nome,
                "lat": lat,
                "lon": lon,
            })
        print(f"  {uf}: {vistas:,} linhas com número, {len(reservatorio)} sorteadas",
              flush=True)
    return casos


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


class Braco:
    """Um caminho de resolução e o placar dele."""

    def __init__(self, nome: str) -> None:
        self.nome = nome
        self.acertos: list[bool] = []
        self.erros: list[float] = []
        self.status: dict[str, int] = {}
        self.opcoes = 0
        self.opcoes_fora = 0

    def anotar(self, caso: dict, lat, lon, nomes: list[str | None]) -> bool:
        certo, erro = avaliar(caso, lat, lon, nomes)
        self.acertos.append(certo)
        if erro is not None:
            self.erros.append(erro)
        return certo

    def contar_opcoes(self, r) -> None:
        self.status[r.status] = self.status.get(r.status, 0) + 1
        self.opcoes += len(r.options)
        self.opcoes_fora += sum(1 for o in r.options if o.fonte != "cnefe")

    def imprimir(self) -> None:
        n = len(self.acertos) or 1
        certo = sum(self.acertos)
        print(f"\n{self.nome}")
        print(f"  municipio correto : {certo}/{len(self.acertos)} ({100 * certo / n:.0f}%)")
        if self.erros:
            p90 = (f"  (p90 {statistics.quantiles(self.erros, n=10)[8]:.2f} km)"
                   if len(self.erros) > 1 else "")
            print(f"  erro ate a casa   : mediana {statistics.median(self.erros):.2f} km{p90}")
        if self.opcoes:
            print(f"  opcoes oferecidas : {self.opcoes}, fora do CNEFE "
                  f"{self.opcoes_fora} ({100 * self.opcoes_fora / self.opcoes:.1f}%)")
        if self.status:
            print("  status            :",
                  ", ".join(f"{k}={v}" for k, v in sorted(self.status.items())))


def _resumo(nome: str, erros: list[float]) -> None:
    if not erros:
        print(f"{nome:<22} sem casos")
        return
    q = statistics.quantiles(erros, n=100)
    print(f"{nome:<22} mediana {statistics.median(erros):7.1f} m | p75 {q[74]:8.1f} | "
          f"p90 {q[89]:9.1f} | <=25 m {100 * sum(1 for e in erros if e <= 25) / len(erros):4.1f}%")


def avaliar_numeracao(n: int, seed: int) -> None:
    """Leave-one-out sobre a numeração: esconde um número e mede a dedução.

    É a única medida honesta do caso `vizinho`, que é o que acontece quando o entregador
    procura um número que o recenseador não visitou. Sorteia só ruas com três números ou
    mais e só posições interiores, porque fora da faixa a resposta é a ponta da rua, não
    uma interpolação.
    """
    con = cnefe._conexao()
    if con is None or not cnefe.tem_numeracao():
        raise SystemExit("Este modo precisa de uma base com numeração (versao_indice 2).")
    campos = ",".join(f"l.{c}" for c in cnefe._campos_log())
    maior = con.execute("SELECT max(log_id) FROM numeracao").fetchone()[0]
    rnd = random.Random(seed)
    novo: list[float] = []
    antigo_: list[float] = []
    vistos: set[int] = set()
    tentativas = 0
    while len(novo) < n and tentativas < n * 20:
        tentativas += 1
        log_id = rnd.randint(1, maior)
        if log_id in vistos:
            continue
        vistos.add(log_id)
        row = con.execute(f"SELECT {campos} FROM logradouro l "
                          "JOIN numeracao u ON u.log_id = l.id "
                          "WHERE l.id = ? AND u.n >= 3", (log_id,)).fetchone()
        if row is None:
            continue
        numeros, pontos = cnefe._numeros(row["id"], row["lat"], row["lon"])
        j = rnd.randrange(1, len(numeros) - 1)
        alvo, (vlat, vlon, _) = numeros[j], pontos[j]

        # A mesma conta do ramo `vizinho` de `cnefe.posicionar`, com o número escondido:
        # em via quilométrica a numeração não acompanha a geografia e o centroide vence.
        if row["raio_m"] >= cnefe.RAIO_TETO_M:
            dlat, dlon = row["lat"] / 1e6, row["lon"] / 1e6
        else:
            lat_a, lon_a, _ = pontos[j - 1]
            lat_b, lon_b, _ = pontos[j + 1]
            t = (alvo - numeros[j - 1]) / (numeros[j + 1] - numeros[j - 1])
            dlat, dlon = lat_a + t * (lat_b - lat_a), lon_a + t * (lon_b - lon_a)
        novo.append(cnefe.distancia_m(dlat, dlon, vlat, vlon))

        ilat, ilon, _ = cnefe._interpolar(row, alvo)
        antigo_.append(cnefe.distancia_m(ilat, ilon, vlat, vlon))

    print(f"{len(novo)} números escondidos em {len(vistos)} ruas sorteadas\n")
    _resumo("v1 (faixa da rua)", antigo_)
    _resumo("v2 (dois vizinhos)", novo)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--amostra", type=int, default=25)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--gabarito", type=Path)
    ap.add_argument("--fonte-csv", type=Path,
                    help="diretório com os zips do CNEFE; sorteia linhas cruas do microdado")
    ap.add_argument("--ufs", nargs="*", default=None,
                    help="UFs a varrer com --fonte-csv (padrão: 4 sorteadas)")
    ap.add_argument("--sem-rede", action="store_true",
                    help="mede só a proposta local, sem gastar cota do ORS")
    ap.add_argument("--com-cep", action="store_true",
                    help="inclui o CEP no texto, como num romaneio real")
    ap.add_argument("--modo-numeracao", action="store_true",
                    help="leave-one-out sobre a numeração; mede o número que não está "
                         "no cadastro, e só isso — ignora as demais opções")
    ap.add_argument("--sem-numeracao", action="store_true",
                    help="finge que a base é v1, para medir o antes e o depois no "
                         "mesmo arquivo")
    args = ap.parse_args()

    if args.modo_numeracao:
        avaliar_numeracao(args.amostra, args.seed)
        return
    if args.sem_numeracao:
        cnefe.FORCAR_V1 = True
        cnefe.limpar_conexao()

    key = None if args.sem_rede else load_config().ors_api_key
    if not args.sem_rede and not key:
        raise SystemExit("Configure a chave do OpenRouteService ou rode com --sem-rede.")

    if args.gabarito:
        casos = ler_gabarito(args.gabarito)
    elif args.fonte_csv:
        ufs = args.ufs or random.Random(args.seed).sample(UFS, 4)
        print(f"varrendo {', '.join(ufs)}", flush=True)
        casos = amostrar_csv(args.amostra, args.seed, args.fonte_csv, ufs, args.com_cep)
    else:
        casos = amostrar(args.amostra, args.seed, args.com_cep)
    print(f"{len(casos)} endereços | base CNEFE: {cnefe.disponivel()}")

    local = Braco("PROPOSTA LOCAL (CNEFE, sem rede)")
    cascata = Braco("CASCATA COMPLETA (CNEFE + ViaCEP + ORS)")
    cru = Braco("ORS CRU (texto direto, primeiro palpite)")
    for i, caso in enumerate(casos, 1):
        p = address_resolver.propor(caso["texto"])
        local.contar_opcoes(p)
        certo = local.anotar(caso, p.lat, p.lon,
                             [p.options[0].municipio] if p.options else [])

        if key:
            r = address_resolver.resolve(caso["texto"], api_key=key)
            cascata.contar_opcoes(r)
            nomes = [r.hit.locality, r.hit.localadmin, r.hit.county] if r.hit else []
            cascata.anotar(caso, r.lat, r.lon, nomes)
            lat, lon, nomes_v = antigo(caso["texto"], key)
            cru.anotar(caso, lat, lon, nomes_v)

        marca = "  " if certo else "!!"
        print(f"{marca} [{i:>3}] {p.status:<14} {caso['municipio'][:22]:<22} "
              f"{caso['texto'][:58]}")

    for braco in (cru, cascata, local):
        if braco.acertos:
            braco.imprimir()


if __name__ == "__main__":
    main()
