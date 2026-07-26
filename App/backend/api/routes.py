import webbrowser
from datetime import date, datetime

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from core.config import AppConfig, load_config, save_config
from core.schemas import GeocodeHit, PlannedStop, RoutePlan, RouteSolveRequest
from services import address_parser, gmaps_export, ocr, ors_client, solver_lkh, tabular
from services.eta import compute_etas
from services.ors_client import OrsError

APP_VERSION = "0.1.0"
MAX_STOPS = 49

router = APIRouter()

_matrix_cache: dict[tuple, dict] = {}


class ConfigUpdate(BaseModel):
    ors_api_key: str | None = None
    optimize_by: str | None = None
    departure_time: str | None = None
    stop_minutes: int | None = None


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
    ocr_texts: list[str] = []
    table_lines: list[str] = []
    for upload in files:
        name = (upload.filename or "").lower()
        content = upload.file.read()
        if not content:
            continue
        if name.endswith(".xls"):
            raise HTTPException(
                400,
                f"O formato .xls antigo não é suportado ('{upload.filename}'). "
                "Salve a planilha como .xlsx ou CSV.",
            )
        try:
            if name.endswith(".csv") or name.endswith(".txt"):
                table_lines.extend(tabular.lines_from_csv(content))
            elif name.endswith((".xlsx", ".xlsm")):
                table_lines.extend(tabular.lines_from_xlsx(content))
            else:
                ocr_texts.append(ocr.extract_text(content))
        except RuntimeError as exc:
            raise HTTPException(400, str(exc))
        except Exception as exc:
            raise HTTPException(422, f"Falha ao processar o arquivo '{upload.filename}': {exc}")

    candidates = address_parser.merge_candidates(
        address_parser.extract_address_candidates("\n".join(ocr_texts)),
        address_parser.extract_address_candidates("\n".join(table_lines), pair_lines=False),
    )
    combined = "\n".join(ocr_texts + table_lines)
    return {"text": combined, "candidates": candidates}


@router.get("/geocode/autocomplete")
def autocomplete(text: str, focus_lat: float | None = None, focus_lon: float | None = None):
    if len(text.strip()) < 2:
        return []
    key = _require_key()
    focus = (focus_lat, focus_lon) if focus_lat is not None and focus_lon is not None else None
    try:
        return ors_client.geocode_autocomplete(key, text, focus=focus)
    except OrsError as exc:
        raise _http_from_ors(exc)


@router.get("/geocode/search")
def search(text: str):
    key = _require_key()
    try:
        return ors_client.geocode_search(key, text)
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


@router.post("/route/solve")
def solve_route(req: RouteSolveRequest):
    if len(req.stops) > MAX_STOPS:
        raise HTTPException(400, f"Máximo de {MAX_STOPS} paradas por rota (limite da matriz do OpenRouteService).")
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

    durations = mat["durations"]
    distances = mat["distances"]
    warnings: list[str] = []
    n = len(coords)
    if any(durations[i][j] is None for i in range(n) for j in range(n) if i != j):
        warnings.append("Alguns pontos não são alcançáveis por via rodoviária; a ordem pode ficar imprecisa.")

    cost = durations if req.optimize_by == "duration" else distances
    try:
        tour = solver_lkh.solve_atsp(cost)
    except RuntimeError as exc:
        raise HTTPException(500, f"Falha na otimização da rota: {exc}")

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
            warnings.append(f"Não foi possível obter o traçado da rota no mapa: {exc.message}")

    return RoutePlan(
        ordered_stops=planned,
        departure_time=req.departure_time,
        return_eta=etas.return_eta.strftime("%H:%M"),
        total_duration_s=etas.total_seconds,
        total_distance_m=total_distance,
        driving_duration_s=etas.driving_seconds,
        geometry=geometry,
        gmaps_urls=gmaps_export.build_gmaps_urls(cycle),
        warnings=warnings,
    )


@router.post("/open-url")
def open_url(payload: OpenUrlPayload):
    if not payload.url.startswith(("https://", "http://")):
        raise HTTPException(400, "URL inválida.")
    webbrowser.open(payload.url)
    return {"opened": True}
