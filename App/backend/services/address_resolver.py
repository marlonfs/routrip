"""Resolve um endereço em coordenada validada, em vez de aceitar o primeiro palpite.

O problema que isto ataca: o geocoder devolve "Rua Alfredo Guedes" de Campinas e de
Piracicaba com a mesma confiança, e pegar `hits[0]` entrega em cidade errada com
aparência de sucesso. Pior, ele inventa: oferece com a mesma cara uma rua que não
existe no município.

Por isso a ordem aqui é cadastro primeiro, geocoder depois. Quem responde "esta rua
existe?" é o CNEFE/IBGE, e só o que ele confirma vira opção para o usuário escolher.
O ORS entra para refinar a casa dentro da rua certa, ou como reserva explicitamente
marcada quando o cadastro não tem nada — nunca como proposta confirmada.
"""

import uuid
from difflib import SequenceMatcher

from core.schemas import (
    AddressOption,
    CepInfo,
    CnefeCep,
    CnefeLogradouro,
    CnefeMunicipio,
    GeocodeHit,
    ParsedAddress,
    ResolveStatus,
    ResolvedAddress,
    ValidationCheck,
)
from services import address_parser, cnefe, ors_client, viacep
from services import br_address_terms as termos
from services.ors_client import OrsError
from services.viacep import CepIndisponivel

SIM_LOGRADOURO_MIN = 0.6
SIM_MUNICIPIO_MIN = 0.85
# Piso para o cadastro responder sozinho. Abaixo disso a rua encontrada ainda é real,
# mas a semelhança com o texto lido é fraca demais para dispensar o olho do usuário.
SIM_CNEFE_AUTO = 0.8
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


def _numero_int(p: ParsedAddress) -> int | None:
    bruto = (p.numero or "").strip()
    return int(bruto) if bruto.isdigit() and len(bruto) <= 5 else None


def _buscar_cnefe(p: ParsedAddress, ancora: CnefeCep | None, municipio: str | None,
                  limite: int = 6) -> list[CnefeLogradouro]:
    if not p.logradouro or not cnefe.busca_por_rua():
        return []
    via = " ".join(x for x in (p.tipo_logradouro, p.logradouro) if x)
    return cnefe.buscar_logradouro(
        via, cod_ibge=ancora.cod_ibge if ancora else None, cep=p.cep,
        municipio=municipio or p.localidade, uf=p.uf,
        numero=_numero_int(p), limite=limite)


def opcao_cnefe(a: CnefeLogradouro, i: int) -> AddressOption:
    tipo = (a.tipo or "").title()
    return AddressOption(
        id=f"c{i}", fonte="cnefe", confirmado=True, label=a.label, lat=a.lat, lon=a.lon,
        logradouro=f"{tipo} {a.nome.title()}".strip(),
        numero=a.numero, numero_confirmado=a.numero_confirmado,
        num_min=a.num_min, num_max=a.num_max,
        municipio=a.municipio.nome if a.municipio else None,
        uf=a.municipio.uf if a.municipio else None,
        cep=a.cep, similaridade=a.similaridade,
    )


def opcao_ors(h: GeocodeHit, i: int) -> AddressOption:
    return AddressOption(
        id=f"o{i}", fonte="ors", confirmado=False, label=h.label, lat=h.lat, lon=h.lon,
        logradouro=h.street, numero=int(h.housenumber) if (h.housenumber or "").isdigit() else None,
        municipio=h.locality or h.localadmin or h.county, uf=h.region_a,
        cep=h.postalcode, similaridade=h.confidence,
    )


def _status_cnefe(a: CnefeLogradouro) -> ResolveStatus:
    if a.similaridade < SIM_CNEFE_AUTO:
        return "nao_verificado"
    return "verificado" if a.numero_confirmado else "provavel"


def _refinar_no_ors(a: CnefeLogradouro, api_key: str) -> tuple[float, float] | None:
    """A rua já está decidida pelo cadastro; aqui só se tenta melhorar onde fica a casa.

    Vale a chamada apenas quando o número está fora da faixa cadastrada — dentro dela a
    interpolação já erra cerca de 35 m. Só aceita `layer=address` com número dentro do
    raio da própria rua: qualquer coisa fora disso é outra via.
    """
    if a.numero is None or a.numero_confirmado or a.municipio is None:
        return None
    rua = f"{(a.tipo or '').title()} {a.nome.title()}".strip()
    alvo = f"{rua}, {a.numero}, {a.municipio.nome} - {a.municipio.uf}"
    try:
        hits = ors_client.geocode_search(
            api_key, alvo, layers="address",
            boundary_circle=(a.lat, a.lon, max(1.0, a.raio_m * 2 / 1000)))
    except OrsError:
        return None
    limite = max(float(a.raio_m), DIST_TOLERANCIA_MIN_M)
    for h in hits:
        if (h.layer == "address" and h.housenumber
                and cnefe.distancia_m(h.lat, h.lon, a.lat, a.lon) <= limite):
            return h.lat, h.lon
    return None


def _municipio_confere(hit: GeocodeHit, esperado: str | None) -> bool:
    if not esperado:
        return True
    nomes = [n for n in (hit.locality, hit.localadmin, hit.county) if n]
    return any(_similar(n, esperado) >= SIM_MUNICIPIO_MIN for n in nomes)


def _cnefe_confirma(hit: GeocodeHit, muni: CnefeMunicipio | None) -> ValidationCheck | None:
    """Reprova a rua que o geocoder inventou. Sem município resolvido não dá para
    afirmar nada, e um check ausente é melhor que um check chutado."""
    if muni is None or not cnefe.busca_por_rua():
        return None
    rua = hit.street or (hit.label or "").split(",")[0]
    if not rua.strip():
        return None
    achados = cnefe.buscar_logradouro(rua, cod_ibge=muni.cod_ibge, limite=1)
    return ValidationCheck(
        nome="cnefe_confirma", ok=bool(achados),
        detalhe=achados[0].label if achados else f"'{rua}' não consta em {muni.nome}")


def _validar(hit: GeocodeHit, p: ParsedAddress, ancora: CnefeCep | None,
             municipio: str | None, muni: CnefeMunicipio | None = None
             ) -> list[ValidationCheck]:
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
    confirma = _cnefe_confirma(hit, muni)
    if confirma:
        checks.append(confirma)
    return checks


def _escolher(hits: list[GeocodeHit], p: ParsedAddress, ancora: CnefeCep | None,
              municipio: str | None, muni: CnefeMunicipio | None = None
              ) -> tuple[GeocodeHit, list[ValidationCheck], int] | None:
    """Prefere o hit que passa em tudo; se nenhum passa, devolve o que falha menos —
    o chamador decide se isso é bom o bastante pelo status."""
    melhor = None
    for hit in hits:
        checks = _validar(hit, p, ancora, municipio, muni)
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


def propor(text: str, *, item_id: str | None = None, limite: int = 6) -> ResolvedAddress:
    """As opções reais para um texto lido, sem tocar na rede.

    Depois do OCR são dezenas de endereços de uma vez; consultar ViaCEP e ORS para cada
    um levaria minutos e gastaria cota para, no fim, oferecer ruas que podem não existir.
    O cadastro local responde em milissegundos e só devolve o que existe.
    """
    avisos: list[str] = []
    p = address_parser.parse_address(text)
    out = ResolvedAddress(id=item_id or uuid.uuid4().hex[:8], status="nao_encontrado",
                          label=text.strip(), parsed=p)

    cep = normalizar_cep(p.cep)
    ancora = cnefe.lookup(cep) if cep else None
    if cep and ancora is None and cnefe.disponivel():
        avisos.append("cep_fora_da_base")
    if ancora and ancora.generico:
        avisos.append("cep_generico")
    out.cnefe = ancora

    achados = _buscar_cnefe(p, ancora, None, limite)
    out.options = [opcao_cnefe(a, i) for i, a in enumerate(achados)]
    if achados:
        melhor = achados[0]
        out.status = _status_cnefe(melhor)
        out.lat, out.lon, out.label, out.etapa = melhor.lat, melhor.lon, melhor.label, "cnefe"
    elif ancora:
        # A rua não foi reconhecida, mas o CEP existe: o centroide dele ao menos põe a
        # parada no bairro certo enquanto o usuário confere.
        out.status = "aproximado"
        out.lat, out.lon, out.etapa = ancora.lat, ancora.lon, "centroide_cep"
        out.label = address_parser.format_address(p) or out.label
    elif cnefe.busca_por_rua():
        # O modal trata os dois casos de formas opostas: sem cidade ele pergunta a
        # cidade, porque existem milhares de "Rua São José" no país; com a cidade
        # conhecida e a rua ausente, ele oferece o caminho de exceção.
        conhecido = cnefe.resolver_municipio(cep=p.cep, municipio=p.localidade, uf=p.uf)
        avisos.append("rua_fora_do_cadastro" if conhecido else "municipio_desconhecido")

    out.avisos = avisos
    return out


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

    # O cadastro do IBGE responde primeiro. Quando ele reconhece a rua, o ORS não é
    # consultado para escolher nada — no máximo para achar a casa dentro dela.
    achados = _buscar_cnefe(p, ancora, municipio)
    if achados:
        melhor = achados[0]
        out.options = [opcao_cnefe(a, i) for i, a in enumerate(achados)]
        out.status = _status_cnefe(melhor)
        out.lat, out.lon, out.label, out.etapa = melhor.lat, melhor.lon, melhor.label, "cnefe"
        preciso = _refinar_no_ors(melhor, api_key)
        if preciso:
            out.lat, out.lon = preciso
            out.etapa = "cnefe+ors"
        out.avisos = avisos
        return out

    muni = cnefe.resolver_municipio(cod_ibge=ancora.cod_ibge if ancora else None,
                                    cep=cep, municipio=municipio, uf=p.uf)
    if muni is not None and p.logradouro and cnefe.busca_por_rua():
        avisos.append("rua_fora_do_cadastro")

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
        escolha = _escolher(hits, p, ancora, municipio, muni)
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

    # Chegar aqui significa que o cadastro não reconheceu a rua. O que o geocoder achou
    # entra como reserva, sempre marcada: é palpite, não confirmação.
    out.options = [opcao_ors(h, i) for i, h in enumerate(alternativas[:8])]
    out.avisos = avisos
    return out
