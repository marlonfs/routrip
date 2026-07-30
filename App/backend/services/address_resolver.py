"""Resolve um endereço em coordenada validada, em vez de aceitar o primeiro palpite.

O problema que isto ataca: o geocoder devolve "Rua Alfredo Guedes" de Campinas e de
Piracicaba com a mesma confiança, e pegar `hits[0]` entrega em cidade errada com
aparência de sucesso. Aqui o CEP vira âncora — via ViaCEP para os nomes e via CNEFE
para a coordenada — e todo resultado é conferido contra ela antes de ser aceito.
"""

import uuid
from difflib import SequenceMatcher

from core.schemas import (
    CepInfo,
    CnefeCep,
    GeocodeHit,
    ParsedAddress,
    ResolvedAddress,
    ValidationCheck,
)
from services import address_parser, cnefe, ors_client, viacep
from services import br_address_terms as termos
from services.ors_client import OrsError
from services.viacep import CepIndisponivel

SIM_LOGRADOURO_MIN = 0.6
SIM_MUNICIPIO_MIN = 0.85
DIST_TOLERANCIA_MIN_M = 400.0
LAYERS_ENDERECO = "address,street,venue"
# O Pelias no Brasil raramente devolve layer=address; "street" é o caso normal e
# precisa ser aceito, mas "locality" significa que ele só achou a cidade.
LAYERS_ACEITAVEIS = {"address", "street", "venue"}

_CONFUSAO_OCR = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "B": "8"})


def _similar(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, termos.normalizar(a), termos.normalizar(b)).ratio()


def normalizar_cep(bruto: str | None) -> str | None:
    if not bruto:
        return None
    digitos = "".join(c for c in bruto.translate(_CONFUSAO_OCR) if c.isdigit())
    return digitos if len(digitos) == 8 else None


def _texto_livre(p: ParsedAddress) -> str:
    return address_parser.format_address(p)


def _separar_tipo(logradouro: str) -> tuple[str | None, str]:
    """O ViaCEP devolve "Avenida Pádua Dias" num campo só; o parser guarda tipo e nome
    separados. Sem separar, a junção vira "Avenida Avenida Pádua Dias"."""
    m = termos.TIPO_LOGRADOURO.match(logradouro)
    if not m:
        return None, logradouro
    return termos.expandir_tipo(m.group(1)), logradouro[m.end():].strip(" .,-")


def _consultar_cep(cep: str, avisos: list[str]) -> CepInfo | None:
    try:
        return viacep.consultar(cep)
    except CepIndisponivel:
        avisos.append("cep_nao_verificado")
        return None


def _mesclar(p: ParsedAddress, info: CepInfo, avisos: list[str]) -> ParsedAddress:
    """Localidade e UF sempre vêm do CEP; o logradouro só é substituído se combinar.

    Divergência aqui costuma significar que o parser pegou o CEP do emitente da nota
    junto com o logradouro do destinatário — nesse caso o logradouro lido é a fonte
    mais confiável, e o CEP é que deve ser desconsiderado como âncora."""
    saida = p.model_copy()
    saida.localidade = info.localidade or p.localidade
    saida.uf = info.uf or p.uf
    if info.bairro and not p.bairro:
        saida.bairro = info.bairro
    if info.logradouro:
        tipo, nome = _separar_tipo(info.logradouro)
        if _similar(p.logradouro, nome) >= SIM_LOGRADOURO_MIN or not p.logradouro:
            saida.tipo_logradouro = tipo or p.tipo_logradouro
            saida.logradouro = nome
        else:
            avisos.append("cep_logradouro_divergente")
    return saida


def _degraus(p: ParsedAddress, ancora: CnefeCep | None, info: CepInfo | None,
             origin: tuple[float, float] | None):
    """Do mais restrito ao mais permissivo. Cada degrau é (nome, função)."""
    via = " ".join(x for x in (p.tipo_logradouro, p.logradouro) if x)
    endereco = f"{via}, {p.numero}" if p.numero and via else via
    circulo_cep = (ancora.lat, ancora.lon, max(2.0, ancora.raio_m * 3 / 1000)) if ancora else None
    circulo_mun = None
    if ancora and ancora.municipio:
        m = ancora.municipio
        circulo_mun = (m.lat, m.lon, max(5.0, m.raio_m * 1.5 / 1000))

    degraus = []
    if endereco and (p.localidade or p.cep):
        # Sem `neighbourhood`: com bairro preenchido o Pelias desiste do endereço e
        # devolve a cidade (layer=locality), que é justamente o que queremos evitar.
        degraus.append(("structured", lambda key: ors_client.geocode_search_structured(
            key, address=endereco, locality=p.localidade, region=p.uf, postalcode=p.cep)))
    if circulo_cep and endereco:
        degraus.append(("circulo_cep", lambda key: ors_client.geocode_search(
            key, _texto_livre(p), layers=LAYERS_ENDERECO, boundary_circle=circulo_cep)))
    if circulo_mun and endereco:
        degraus.append(("circulo_municipio", lambda key: ors_client.geocode_search(
            key, _texto_livre(p), layers=LAYERS_ENDERECO, boundary_circle=circulo_mun)))
        sem_numero = p.model_copy(update={"numero": None, "sem_numero": False})
        degraus.append(("sem_numero", lambda key: ors_client.geocode_search(
            key, _texto_livre(sem_numero), layers=LAYERS_ENDERECO,
            boundary_circle=circulo_mun)))
        so_rua = sem_numero.model_copy(update={"bairro": None})
        degraus.append(("so_rua", lambda key: ors_client.geocode_search(
            key, _texto_livre(so_rua), layers="street", boundary_circle=circulo_mun)))
    degraus.append(("livre", lambda key: ors_client.geocode_search(
        key, _texto_livre(p) or "", focus=origin)))
    return degraus


def _municipio_confere(hit: GeocodeHit, esperado: str | None) -> bool:
    if not esperado:
        return True
    nomes = [n for n in (hit.locality, hit.localadmin, hit.county) if n]
    return any(_similar(n, esperado) >= SIM_MUNICIPIO_MIN for n in nomes)


def _validar(hit: GeocodeHit, p: ParsedAddress, ancora: CnefeCep | None,
             municipio: str | None) -> list[ValidationCheck]:
    checks = [
        ValidationCheck(nome="camada", ok=hit.layer in LAYERS_ACEITAVEIS,
                        detalhe=hit.layer),
        ValidationCheck(nome="uf", ok=not p.uf or not hit.region_a
                        or hit.region_a.upper() == p.uf.upper(), detalhe=hit.region_a),
        ValidationCheck(nome="municipio", ok=_municipio_confere(hit, municipio),
                        detalhe=hit.locality or hit.localadmin or hit.county),
    ]
    if ancora:
        d = cnefe.distancia_m(hit.lat, hit.lon, ancora.lat, ancora.lon)
        limite = max(float(ancora.raio_m), DIST_TOLERANCIA_MIN_M)
        checks.append(ValidationCheck(nome="distancia", ok=d <= limite,
                                      detalhe=f"{d / 1000:.1f} km (limite {limite / 1000:.1f} km)"))
    return checks


def _escolher(hits: list[GeocodeHit], p: ParsedAddress, ancora: CnefeCep | None,
              municipio: str | None) -> tuple[GeocodeHit, list[ValidationCheck], int] | None:
    """Prefere o hit que passa em tudo; se nenhum passa, devolve o que falha menos —
    o chamador decide se isso é bom o bastante pelo status."""
    melhor = None
    for hit in hits:
        checks = _validar(hit, p, ancora, municipio)
        falhas = sum(1 for c in checks if not c.ok)
        if falhas == 0:
            return hit, checks, 0
        if melhor is None or falhas < melhor[2]:
            melhor = (hit, checks, falhas)
    return melhor


def _falhou(checks: list[ValidationCheck], nome: str) -> bool:
    return any(c.nome == nome and not c.ok for c in checks)


def _refinar(hit: GeocodeHit, ancora: CnefeCep | None) -> tuple[float, float] | None:
    """O ORS não tem numeração de rua no Brasil: `layer=street` devolve o centroide da
    via inteira, que numa avenida de 3 km erra por quilômetros. O centroide do CEP no
    CNEFE cobre um trecho e é mais perto do número procurado.

    Só troca quando o logradouro do CNEFE confirma que o CEP é da mesma rua — sem essa
    conferência, um CEP de emitente lido por engano moveria a parada para outro bairro.
    """
    if not ancora or ancora.generico or hit.layer != "street" or hit.housenumber:
        return None
    if _similar(ancora.logradouro, hit.street or hit.label) < SIM_LOGRADOURO_MIN:
        return None
    return ancora.lat, ancora.lon


def _aprovar(hit: GeocodeHit, checks: list[ValidationCheck], falhas: int) -> str | None:
    if falhas == 0:
        return "verificado" if hit.layer in ("address", "venue") else "provavel"
    if falhas == 1 and _falhou(checks, "distancia"):
        # A distância existe para pegar município errado, e o município já conferiu por
        # nome. Sozinha ela reprova acerto: o CEP cobre um trecho da via e o hit é o
        # centroide da via inteira, então numa avenida longa os dois pontos ficam a
        # centenas de metros um do outro sem que nenhum esteja errado.
        return "provavel"
    return None


def resolve(text: str, *, api_key: str, origin: tuple[float, float] | None = None,
            item_id: str | None = None) -> ResolvedAddress:
    avisos: list[str] = []
    p = address_parser.parse_address(text)
    out = ResolvedAddress(id=item_id or uuid.uuid4().hex[:8], status="nao_encontrado",
                          label=text.strip(), parsed=p)

    cep = normalizar_cep(p.cep)
    info = _consultar_cep(cep, avisos) if cep else None
    if cep and info is None and "cep_nao_verificado" not in avisos:
        avisos.append("cep_inexistente")
    if info:
        p = _mesclar(p, info, avisos)
        out.parsed = p
        out.cep_info = info

    ancora = cnefe.lookup(cep) if cep else None
    if cep and ancora is None and cnefe.disponivel():
        avisos.append("cep_fora_da_base")
    if ancora and ancora.generico:
        avisos.append("cep_generico")
    out.cnefe = ancora

    municipio = info.localidade if info else p.localidade
    if ancora and ancora.municipio and ancora.municipio.nome:
        municipio = municipio or ancora.municipio.nome

    vistos: set[tuple[float, float]] = set()
    alternativas: list[GeocodeHit] = []
    # O último degrau é o mais permissivo, então guardar "o resultado mais recente"
    # deixaria o pior palpite sobrescrever um quase-acerto de um degrau anterior.
    parcial: tuple[int, str, GeocodeHit, list[ValidationCheck]] | None = None
    for nome, chamada in _degraus(p, ancora, info, origin):
        try:
            hits = chamada(api_key)
        except OrsError:
            # Um parâmetro não suportado no plano gratuito não pode derrubar a
            # importação inteira: só custa este degrau.
            continue
        if not hits:
            continue
        for h in hits:
            chave = (round(h.lat, 5), round(h.lon, 5))
            if chave not in vistos:
                vistos.add(chave)
                alternativas.append(h)
        escolha = _escolher(hits, p, ancora, municipio)
        if escolha is None:
            continue
        hit, checks, falhas = escolha
        aprovado = _aprovar(hit, checks, falhas)
        if aprovado:
            out.status = aprovado
            out.hit, out.checks, out.lat, out.lon = hit, checks, hit.lat, hit.lon
            out.label = hit.label
            out.etapa = nome
            preciso = _refinar(hit, ancora)
            if preciso:
                out.lat, out.lon = preciso
                out.etapa = f"{nome}+cep"
            break
        if parcial is None or falhas < parcial[0]:
            parcial = (falhas, nome, hit, checks)

    if out.status == "nao_encontrado" and parcial:
        _, nome, hit, checks = parcial
        out.hit, out.checks, out.etapa = hit, checks, nome
        out.lat, out.lon, out.label = hit.lat, hit.lon, hit.label
        out.status = "divergente"

    if ancora and (out.status == "nao_encontrado"
                   or (out.status == "divergente" and _falhou(out.checks, "municipio"))):
        # Município errado é o erro que faz o entregador rodar 100 km; o centroide do
        # CEP erra por quarteirões. Quando só a distância falha, trocar o endereço pelo
        # centroide perde o número da casa sem ganhar nada.
        out.status = "aproximado"
        out.lat, out.lon = ancora.lat, ancora.lon
        out.label = address_parser.format_address(p) or out.label
        out.etapa = out.etapa or "centroide_cep"

    sem_ancora = not ancora and not municipio
    cep_suspeito = {"cep_inexistente", "cep_nao_verificado"} & set(avisos)
    if out.status in ("verificado", "provavel"):
        if sem_ancora and cep_suspeito:
            # Nada confirmou o município: o CEP lido não existe e o texto não trouxe
            # cidade. O geocoder devolve rua homônima em qualquer estado com a mesma
            # cara de sucesso, então isto tem que passar pelo olho do usuário.
            out.status = "nao_verificado"
        elif sem_ancora or "cep_nao_verificado" in avisos:
            out.status = "provavel"

    out.alternatives = alternativas[:8]
    out.avisos = avisos
    return out
