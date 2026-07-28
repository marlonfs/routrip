from typing import Literal

from pydantic import BaseModel, Field


class AddressCandidate(BaseModel):
    id: str
    raw_text: str
    cleaned: str
    confidence: float


class SpreadsheetSheet(BaseModel):
    name: str
    rows: list[list[str]]
    total_rows: int
    truncated: bool


class SpreadsheetPreview(BaseModel):
    filename: str
    sheets: list[SpreadsheetSheet]


class AddressLines(BaseModel):
    lines: list[str]


class GeocodeHit(BaseModel):
    label: str
    lat: float
    lon: float
    confidence: float = 0.0


class Stop(BaseModel):
    id: str
    label: str
    lat: float
    lon: float


class RouteSolveRequest(BaseModel):
    origin: Stop
    stops: list[Stop] = Field(min_length=1)
    optimize_by: Literal["duration", "distance"] = "duration"
    departure_time: str = "08:00"
    stop_minutes: int = 10
    want_geometry: bool = True


class PlannedStop(BaseModel):
    stop: Stop
    order: int
    eta: str
    departs: str


class RoutePlan(BaseModel):
    ordered_stops: list[PlannedStop]
    departure_time: str
    return_eta: str
    total_duration_s: float
    total_distance_m: float
    driving_duration_s: float
    geometry: list[list[float]] | None = None
    gmaps_urls: list[str]
    warnings: list[str] = []
