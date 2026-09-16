from urllib.parse import quote, urlencode

GMAPS_MAX_WAYPOINTS = 50


def _fmt(point: tuple[float, float]) -> str:
    return f"{point[0]:.6f},{point[1]:.6f}"


def build_gmaps_urls(cycle: list[tuple[float, float]]) -> list[str]:
    """Gera URLs do Google Maps para o ciclo completo [(lat, lon), ...] com
    origem repetida no final. Divide em trechos encadeados de até 50 waypoints."""
    urls = []
    i = 0
    max_span = GMAPS_MAX_WAYPOINTS + 1
    while i < len(cycle) - 1:
        j = min(i + max_span, len(cycle) - 1)
        segment = cycle[i:j + 1]
        params = {
            "api": "1",
            "origin": _fmt(segment[0]),
            "destination": _fmt(segment[-1]),
            "travelmode": "driving",
        }
        waypoints = segment[1:-1]
        if waypoints:
            params["waypoints"] = "|".join(_fmt(p) for p in waypoints)
        urls.append("https://www.google.com/maps/dir/?" + urlencode(params, quote_via=quote))
        i = j
    return urls
