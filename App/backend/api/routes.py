import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from core.config import AppConfig, load_config, save_config
from core.schemas import (
    AddressCandidate,
    AddressLines,
    FleetPlan,
    PlannedStop,
    ResolvedAddress,
    ResolveRequest,
    RoutePlan,
    RouteSolveRequest,
    SpreadsheetPreview,
    VehicleRoute,
)
from services import (
    address_parser,
    address_resolver,
    cnefe,
    gmaps_export,
    ocr,
    ors_client,
    pdf,
    solver_lkh,
    tabular,
    viacep,
)
from services.eta import compute_etas
from services.ors_client import OrsError

APP_VERSION = "0.1.0"
MAX_STOPS = 100

router = APIRouter()

_matrix_cache: dict[tuple, dict] = {}


class ConfigUpdate(BaseModel):
    ors_api_key: str | None = None
    optimize_by: str | None = None
    departure_time: str | None = None
    stop_minutes: int | None = None
    ocr_preprocess: bool | None = None


class ApiKeyPayload(BaseModel):
    api_key: str


class OpenUrlPayload(BaseModel):
    url: str


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"


def _masked_config(cfg: AppConfig) -> dict:
    data = cfg.model_dump()
    data["ors_api_key"] = _mask(cfg.ors_api_key)
    data["ors_key_set"] = bool(cfg.ors_api_key)
    return data


def _require_key() -> str:
    key = load_config().ors_api_key
    if not key:
        raise HTTPException(400, "Configure a chave da API do OpenRouteService nas configurações.")
    return key


def _http_from_ors(exc: OrsError) -> HTTPException:
    if exc.status_code == 429:
        return HTTPException(429, exc.message)
    if exc.status_code in (401, 403):
        return HTTPException(400, exc.message)
    return HTTPException(502, exc.message)


@router.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


@router.get("/config")
def get_config():
    return _masked_config(load_config())


@router.put("/config")
def put_config(update: ConfigUpdate):
    cfg = load_config()
    data = cfg.model_dump()
    for field, value in update.model_dump(exclude_none=True).items():
        data[field] = value
    try:
        new_cfg = AppConfig(**data)
    except ValueError as exc:
        raise HTTPException(400, f"Configuração inválida: {exc}")
    save_config(new_cfg)
    return _masked_config(new_cfg)


@router.post("/config/validate-ors-key")
def validate_ors_key(payload: ApiKeyPayload):
    try:
        ors_client.geocode_search(payload.api_key, "Praça da Sé, São Paulo", size=1)
    except OrsError as exc:
        return {"valid": False, "message": exc.message}
    return {"valid": True, "message": "Chave válida."}


@router.post("/ocr")
def run_ocr(files: list[UploadFile] = File(...)):
    texts: list[str] = []
    for upload in files:
        name = (upload.filename or "").lower()
        content = upload.file.read()
        if not content:
            continue
        try:
            if name.endswith(".pdf"):
                texts.append(pdf.extract_text(content))
            else:
                texts.append(ocr.extract_text(content))
        except RuntimeError as exc:
            raise HTTPException(400, str(exc))
        except Exception as exc:
            raise HTTPException(422, f"Falha ao processar o arquivo '{upload.filename}': {exc}")

    combined = "\n".join(texts)
    candidatos = address_parser.extract_address_candidates(combined)
    return {"text": combined, "candidates": candidatos, "propostas": _propor(candidatos)}


@router.post("/spreadsheet/preview")
def spreadsheet_preview(file: UploadFile = File(...)) -> SpreadsheetPreview:
    name = (file.filename or "").lower()
    if name.endswith(".xls"):
        raise HTTPException(
            400,
            f"O formato .xls antigo não é suportado ('{file.filename}'). "
            "Salve a planilha como .xlsx ou CSV.",
        )
    content = file.file.read()
    try:
        if name.endswith((".xlsx", ".xlsm")):
            sheets = tabular.grid_from_xlsx(content)
        else:
            sheets = tabular.grid_from_csv(content)
    except Exception as exc:
        raise HTTPException(422, f"Falha ao ler a planilha '{file.filename}': {exc}")

    if not any(sheet.rows for sheet in sheets):
        raise HTTPException(422, f"A planilha '{file.filename}' não tem dados.")
    return SpreadsheetPreview(filename=file.filename or "planilha", sheets=sheets)


def _propor(candidatos: list[AddressCandidate]) -> list[ResolvedAddress]:
    """As propostas saem junto com os candidatos porque são de graça: tudo sai da base
    local, sem rede nem cota do ORS. O modal já abre com endereços que existem."""
    return [address_resolver.propor(c.cleaned or c.raw_text, item_id=c.id) for c in candidatos]


@router.post("/addresses/parse")
def parse_addresses(payload: AddressLines):
    candidatos = address_parser.candidates_from_lines(payload.lines)
    return {"candidates": candidatos, "propostas": _propor(candidatos)}


@router.get("/cnefe/buscar")
def cnefe_buscar(texto: str, municipio: str | None = None, uf: str | None = None,
                 cep: str | None = None, cod_ibge: str | None = None,
                 numero: int | None = None, focus_lat: float | None = None,
                 focus_lon: float | None = None, limite: int = 10):
    """Busca manual do modal, para quando a leitura saiu ruim demais para casar sozinha."""
    if not cnefe.busca_por_rua():
        raise HTTPException(503, "A base do CNEFE instalada não tem o índice de ruas. "
                                 "Atualize a base para buscar endereços por nome.")
    if len(texto.strip()) < 3:
        return {"opcoes": [], "municipio": None}
    muni = cnefe.resolver_municipio(cod_ibge=cod_ibge, cep=cep, municipio=municipio, uf=uf)
    if muni is None:
        if focus_lat is None or focus_lon is None:
            raise HTTPException(422, "Informe a cidade (e o estado) para procurar a rua.")
        achados = cnefe.buscar_perto(texto, focus_lat, focus_lon, numero=numero, limite=limite)
    else:
        achados = cnefe.buscar_logradouro(texto, cod_ibge=muni.cod_ibge, numero=numero,
                                          limite=limite)
    # Mesmo formato das propostas da importação: o modal trata escolha manual e
    # automática pelo mesmo caminho.
    opcoes = [address_resolver.opcao_cnefe(a, i) for i, a in enumerate(achados)]
    return {"opcoes": opcoes, "municipio": muni}


@router.get("/address/sugerir")
def address_sugerir(texto: str, focus_lat: float | None = None,
                    focus_lon: float | None = None, limite: int = 8):
    """A caixa de busca do painel. Separada de `/cnefe/buscar` porque os contratos são
    opostos: aqui não existe cidade informada, e faltar base ou chave tem de degradar a
    qualidade da lista, nunca virar erro na cara de quem está digitando."""
    if len(texto.strip()) < 3:
        return []
    foco = (focus_lat, focus_lon) if focus_lat is not None and focus_lon is not None else None
    return address_resolver.sugerir(texto, foco=foco,
                                    api_key=load_config().ors_api_key, limite=limite)


@router.get("/geocode/search")
def search(text: str, focus_lat: float | None = None, focus_lon: float | None = None,
           layers: str | None = None):
    key = _require_key()
    focus = (focus_lat, focus_lon) if focus_lat is not None and focus_lon is not None else None
    try:
        return ors_client.geocode_search(key, text, focus=focus, layers=layers)
    except OrsError as exc:
        raise _http_from_ors(exc)


@router.get("/cep/{cep}")
def consultar_cep(cep: str):
    try:
        info = viacep.consultar(cep)
    except viacep.CepIndisponivel as exc:
        raise HTTPException(503, str(exc))
    if info is None:
        raise HTTPException(404, "CEP não encontrado.")
    return info


@router.get("/cnefe/status")
def cnefe_status():
    return cnefe.status()


@router.get("/cnefe/lookup")
def cnefe_lookup(cep: str):
    achado = cnefe.lookup(cep)
    if achado is None:
        raise HTTPException(404, "CEP ausente na base do CNEFE.")
    return achado


@router.post("/geocode/resolve")
def resolve_address(payload: ResolveRequest):
    """Um endereço por chamada: a cascata custa 1–2 s e um lote de 40 viraria uma
    requisição de um minuto sem progresso nem cancelamento."""
    key = _require_key()
    origin = ((payload.origin_lat, payload.origin_lon)
              if payload.origin_lat is not None and payload.origin_lon is not None else None)
    try:
        return address_resolver.resolve(payload.text, api_key=key, origin=origin,
                                        item_id=payload.id)
    except OrsError as exc:
        raise _http_from_ors(exc)


@router.get("/geocode/reverse")
def reverse(lat: float, lon: float):
    key = _require_key()
    try:
        return ors_client.reverse_geocode(key, lat, lon)
    except OrsError as exc:
        raise _http_from_ors(exc)


def _get_matrix(key: str, coords: list[tuple[float, float]]) -> dict:
    cache_key = (hash(key), tuple((round(lat, 6), round(lon, 6)) for lat, lon in coords))
    if cache_key in _matrix_cache:
        return _matrix_cache[cache_key]
    result = ors_client.matrix(key, coords)
    if len(_matrix_cache) >= 8:
        _matrix_cache.pop(next(iter(_matrix_cache)))
    _matrix_cache[cache_key] = result
    return result


def _prepare(req: RouteSolveRequest):
    """O que o cálculo de um veículo e o da frota têm em comum: validação, hora de
    saída e a matriz (uma só para a frota inteira — a cota do ORS não muda)."""
    if len(req.stops) > MAX_STOPS:
        raise HTTPException(400, f"Máximo de {MAX_STOPS} paradas por rota.")
    key = _require_key()

    try:
        departure = datetime.combine(date.today(), datetime.strptime(req.departure_time, "%H:%M").time())
    except ValueError:
        raise HTTPException(400, "Hora de saída inválida. Use o formato HH:MM.")

    coords = [(req.origin.lat, req.origin.lon)] + [(s.lat, s.lon) for s in req.stops]
    try:
        mat = _get_matrix(key, coords)
    except OrsError as exc:
        raise _http_from_ors(exc)

    warnings: list[str] = []
    durations = mat["durations"]
    n = len(coords)
    if any(durations[i][j] is None for i in range(n) for j in range(n) if i != j):
        warnings.append("Alguns pontos não são alcançáveis por via rodoviária; a ordem pode ficar imprecisa.")
    return key, departure, coords, mat, warnings


def _build_route(req: RouteSolveRequest, tour: list[int], coords, mat, departure,
                 key: str, geometry_warnings: list[str]) -> dict:
    """Campos de uma rota fechada a partir do tour (tour[0] = origem, índices da
    matriz): ETAs, distância, traçado e links do Google Maps."""
    durations = mat["durations"]
    distances = mat["distances"]
    etas = compute_etas(tour, durations, departure, req.stop_minutes * 60)

    ordered = [req.stops[i - 1] for i in tour[1:]]
    planned = [
        PlannedStop(
            stop=stop,
            order=k + 1,
            eta=etas.arrivals[k].strftime("%H:%M"),
            departs=etas.departures[k].strftime("%H:%M"),
        )
        for k, stop in enumerate(ordered)
    ]

    total_distance = 0.0
    cycle_indices = tour + [0]
    for a, b in zip(cycle_indices, cycle_indices[1:]):
        total_distance += distances[a][b] or 0.0

    cycle = [coords[0]] + [(s.lat, s.lon) for s in ordered] + [coords[0]]
    geometry = None
    if req.want_geometry:
        try:
            geometry = ors_client.directions_geometry(key, cycle)
        except OrsError as exc:
            geometry_warnings.append(f"Não foi possível obter o traçado da rota no mapa: {exc.message}")

    return dict(
        ordered_stops=planned,
        return_eta=etas.return_eta.strftime("%H:%M"),
        total_duration_s=etas.total_seconds,
        total_distance_m=total_distance,
        driving_duration_s=etas.driving_seconds,
        geometry=geometry,
        gmaps_urls=gmaps_export.build_gmaps_urls(cycle),
        _return_dt=etas.return_eta,
    )


@router.post("/route/solve")
def solve_route(req: RouteSolveRequest):
    key, departure, coords, mat, warnings = _prepare(req)

    cost = mat["durations"] if req.optimize_by == "duration" else mat["distances"]
    try:
        tour = solver_lkh.solve_atsp(cost)
    except RuntimeError as exc:
        raise HTTPException(500, f"Falha na otimização da rota: {exc}")

    route = _build_route(req, tour, coords, mat, departure, key, warnings)
    route.pop("_return_dt")
    return RoutePlan(departure_time=req.departure_time, warnings=warnings, **route)


@router.post("/route/solve-fleet")
def solve_fleet(req: RouteSolveRequest):
    """Vários veículos saindo e voltando ao mesmo ponto de partida. Por tempo, o
    objetivo é o último veículo voltar o mais cedo possível (MINMAX, com o tempo de
    atendimento dentro do custo); por distância, a menor soma de km da frota (MINSUM)."""
    key, departure, coords, mat, warnings = _prepare(req)

    vehicles = min(req.vehicles, len(req.stops))
    if vehicles < req.vehicles:
        warnings.append(
            f"Há só {len(req.stops)} {'parada' if len(req.stops) == 1 else 'paradas'} para "
            f"{req.vehicles} veículos: {vehicles} {'sai' if vehicles == 1 else 'saem'}, "
            "cada um com pelo menos uma parada."
        )

    by_time = req.optimize_by == "duration"
    try:
        tours = solver_lkh.solve_mtsp(
            mat["durations"] if by_time else mat["distances"],
            vehicles,
            objective="minmax" if by_time else "minsum",
            service_s=req.stop_minutes * 60 if by_time else 0,
        )
    except RuntimeError as exc:
        raise HTTPException(500, f"Falha na otimização da frota: {exc}")

    # Um traçado por veículo: em paralelo, como os blocos de matriz do ORS.
    geometry_warnings: list[list[str]] = [[] for _ in tours]
    with ThreadPoolExecutor(ors_client.BLOCOS_PARALELOS) as pool:
        built = list(pool.map(
            lambda k: _build_route(req, [0, *tours[k]], coords, mat, departure, key,
                                   geometry_warnings[k]),
            range(len(tours)),
        ))
    for ws in geometry_warnings:
        for w in ws:
            if w not in warnings:
                warnings.append(w)

    last_return = max(r.pop("_return_dt") for r in built)
    routes_out = [VehicleRoute(vehicle=k + 1, **r) for k, r in enumerate(built)]
    return FleetPlan(
        routes=routes_out,
        departure_time=req.departure_time,
        total_distance_m=sum(r.total_distance_m for r in routes_out),
        driving_duration_s=sum(r.driving_duration_s for r in routes_out),
        makespan_s=(last_return - departure).total_seconds(),
        last_return_eta=last_return.strftime("%H:%M"),
        warnings=warnings,
    )


@router.post("/open-url")
def open_url(payload: OpenUrlPayload):
    if not payload.url.startswith(("https://", "http://")):
        raise HTTPException(400, "URL inválida.")
    webbrowser.open(payload.url)
    return {"opened": True}
