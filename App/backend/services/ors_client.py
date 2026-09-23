from concurrent.futures import ThreadPoolExecutor

import httpx

from core.schemas import GeocodeHit
from services.br_address_terms import expandir_abreviacoes as expand_abbreviations

BASE = "https://api.openrouteservice.org"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
MATRIX_MAX_ROUTES = 3500
# Blocos da matriz e pernas do traçado saem em paralelo. Uma rota de 100 paradas são 3 de
# cada, bem dentro do limite por minuto do plano gratuito.
BLOCOS_PARALELOS = 3

# Um cliente só para o processo: `httpx.request` abria conexão e TLS novos a cada
# chamada, e a cascata de geocodificação faz várias seguidas para o mesmo host. O
# cliente é thread-safe e atende o threadpool do FastAPI.
_client = httpx.Client(base_url=BASE, timeout=TIMEOUT,
                       limits=httpx.Limits(max_keepalive_connections=8, keepalive_expiry=60))


class OrsError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _friendly_error(resp: httpx.Response) -> OrsError:
    detail = ""
    try:
        body = resp.json()
        detail = body.get("error", {}).get("message") or body.get("error") or ""
        if isinstance(detail, dict):
            detail = str(detail)
    except Exception:
        pass
    code = resp.status_code
    if code in (401, 403):
        msg = "Chave da API do OpenRouteService inválida ou sem permissão."
    elif code == 429:
        msg = "Limite de requisições do OpenRouteService atingido. Aguarde um minuto e tente novamente."
    elif code == 404:
        msg = "O OpenRouteService não encontrou rota entre os pontos informados."
    else:
        msg = f"Erro do OpenRouteService ({code})."
    if detail:
        msg += f" Detalhe: {detail}"
    return OrsError(code, msg)


def _request(method: str, path: str, api_key: str, *, params=None, json=None) -> dict:
    headers = {"Authorization": api_key, "Accept": "application/json"}
    try:
        resp = _client.request(method, path, params=params, json=json, headers=headers)
    except httpx.HTTPError as exc:
        raise OrsError(0, f"Falha de conexão com o OpenRouteService: {exc}") from exc
    if resp.status_code != 200:
        raise _friendly_error(resp)
    return resp.json()


_PROPS = ("layer", "accuracy", "match_type", "street", "housenumber", "neighbourhood",
          "locality", "localadmin", "county", "region_a", "postalcode")


def _parse_hits(geojson: dict) -> list[GeocodeHit]:
    hits = []
    for feat in geojson.get("features", []):
        lon, lat = feat["geometry"]["coordinates"][:2]
        props = feat.get("properties", {})
        hits.append(GeocodeHit(
            label=props.get("label", ""),
            lat=lat,
            lon=lon,
            confidence=props.get("confidence", 0.0),
            **{name: props.get(name) for name in _PROPS},
        ))
    return hits


def geocode_search(api_key: str, text: str, size: int = 5,
                   country: str = "BR",
                   focus: tuple[float, float] | None = None,
                   layers: str | None = None,
                   boundary_circle: tuple[float, float, float] | None = None) -> list[GeocodeHit]:
    params: dict = {"text": expand_abbreviations(text), "size": size,
                    "boundary.country": country}
    if focus:
        params["focus.point.lat"] = focus[0]
        params["focus.point.lon"] = focus[1]
    if layers:
        params["layers"] = layers
    if boundary_circle:
        lat, lon, radius_km = boundary_circle
        params["boundary.circle.lat"] = lat
        params["boundary.circle.lon"] = lon
        params["boundary.circle.radius"] = radius_km
    return _parse_hits(_request("GET", "/geocode/search", api_key, params=params))


def geocode_search_structured(api_key: str, *, address: str | None = None,
                              neighbourhood: str | None = None,
                              locality: str | None = None,
                              region: str | None = None,
                              postalcode: str | None = None,
                              country: str = "BRA",
                              size: int = 5) -> list[GeocodeHit]:
    params: dict = {"country": country, "size": size}
    for name, value in (("address", address), ("neighbourhood", neighbourhood),
                        ("locality", locality), ("region", region),
                        ("postalcode", postalcode)):
        if value:
            params[name] = expand_abbreviations(value) if name == "address" else value
    return _parse_hits(_request("GET", "/geocode/search/structured", api_key, params=params))


def geocode_autocomplete(api_key: str, text: str,
                         focus: tuple[float, float] | None = None,
                         country: str = "BR",
                         layers: str | None = None) -> list[GeocodeHit]:
    params = {"text": expand_abbreviations(text), "size": 8, "boundary.country": country}
    if focus:
        params["focus.point.lat"] = focus[0]
        params["focus.point.lon"] = focus[1]
    if layers:
        params["layers"] = layers
    return _parse_hits(_request("GET", "/geocode/autocomplete", api_key, params=params))


def reverse_geocode(api_key: str, lat: float, lon: float) -> GeocodeHit | None:
    params = {"point.lat": lat, "point.lon": lon, "size": 1}
    hits = _parse_hits(_request("GET", "/geocode/reverse", api_key, params=params))
    return hits[0] if hits else None


def matrix(api_key: str, coords_latlon: list[tuple[float, float]]) -> dict:
    """Matriz de durações (s) e distâncias (m). Entrada e saída em lat-lon;
    a conversão para o lon-lat do ORS acontece somente aqui. O teto é de pares,
    não de pontos: acima de MATRIX_MAX_ROUTES o ORS devolve o erro 6004, o que
    limita a matriz completa a 59×59. Daí em diante ela é montada em blocos: faixas
    de linhas contra todos os destinos e, se nem uma linha inteira couber (acima de
    MATRIX_MAX_ROUTES pontos), também em faixas de colunas. Não há teto de pontos por
    requisição — só de pares —, então o número de requisições cresce com n²."""
    locations = [[lon, lat] for lat, lon in coords_latlon]
    n = len(locations)
    body = {"locations": locations, "metrics": ["duration", "distance"]}
    if n * n <= MATRIX_MAX_ROUTES:
        data = _request("POST", "/v2/matrix/driving-car", api_key, json=body)
        return {"durations": data["durations"], "distances": data["distances"]}

    colunas = min(n, MATRIX_MAX_ROUTES)
    linhas = max(1, MATRIX_MAX_ROUTES // colunas)
    blocos = [(list(range(inicio_l, min(inicio_l + linhas, n))), inicio_c)
              for inicio_l in range(0, n, linhas) for inicio_c in range(0, n, colunas)]

    def pedir(bloco: tuple[list[int], int]) -> dict:
        sources, inicio_c = bloco
        pedido = {**body, "sources": sources}
        if colunas < n:
            pedido["destinations"] = list(range(inicio_c, min(inicio_c + colunas, n)))
        return _request("POST", "/v2/matrix/driving-car", api_key, json=pedido)

    with ThreadPoolExecutor(BLOCOS_PARALELOS) as pool:
        respostas = list(pool.map(pedir, blocos))

    # `map` devolve na ordem dos blocos: faixas de linhas em sequência e, dentro de cada
    # uma, as faixas de colunas da esquerda para a direita.
    durations: list[list] = [[] for _ in range(n)]
    distances: list[list] = [[] for _ in range(n)]
    for (sources, _), data in zip(blocos, respostas):
        for k, origem in enumerate(sources):
            durations[origem].extend(data["durations"][k])
            distances[origem].extend(data["distances"][k])
    return {"durations": durations, "distances": distances}


def _decode_polyline5(encoded: str) -> list[list[float]]:
    coords, index, lat, lon = [], 0, 0, 0
    while index < len(encoded):
        for which in (0, 1):
            shift, result = 0, 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if which == 0:
                lat += delta
            else:
                lon += delta
        coords.append([lat / 1e5, lon / 1e5])
    return coords


def directions_geometry(api_key: str,
                        coords_latlon: list[tuple[float, float]]) -> list[list[float]]:
    """Geometria da rota (lista [lat, lon]) passando pelos pontos na ordem dada.
    Divide em pernas de até 50 pontos (limite do ORS)."""
    pernas = []
    i = 0
    while i < len(coords_latlon) - 1:
        j = min(i + 49, len(coords_latlon) - 1)
        pernas.append(coords_latlon[i:j + 1])
        i = j

    def pedir(chunk: list[tuple[float, float]]) -> list[list[float]]:
        body = {"coordinates": [[lon, lat] for lat, lon in chunk]}
        data = _request("POST", "/v2/directions/driving-car", api_key, json=body)
        return _decode_polyline5(data["routes"][0]["geometry"])

    with ThreadPoolExecutor(BLOCOS_PARALELOS) as pool:
        partes = list(pool.map(pedir, pernas))

    geometry: list[list[float]] = []
    for part in partes:
        if geometry and part and geometry[-1] == part[0]:
            part = part[1:]
        geometry.extend(part)
    return geometry
