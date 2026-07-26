from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class EtaResult:
    arrivals: list[datetime] = field(default_factory=list)
    departures: list[datetime] = field(default_factory=list)
    return_eta: datetime = None
    driving_seconds: float = 0.0
    total_seconds: float = 0.0


def compute_etas(tour: list[int], durations: list[list[float]],
                 departure: datetime, stop_seconds: int) -> EtaResult:
    """ETAs para cada parada do tour (tour[0] = origem), incluindo retorno à origem."""
    result = EtaResult()
    t = departure
    for k in range(1, len(tour)):
        a, b = tour[k - 1], tour[k]
        leg = durations[a][b] or 0.0
        result.driving_seconds += leg
        t += timedelta(seconds=leg)
        result.arrivals.append(t)
        t += timedelta(seconds=stop_seconds)
        result.departures.append(t)

    last = tour[-1]
    leg = durations[last][tour[0]] or 0.0
    result.driving_seconds += leg
    result.return_eta = t + timedelta(seconds=leg)
    result.total_seconds = (result.return_eta - departure).total_seconds()
    return result
