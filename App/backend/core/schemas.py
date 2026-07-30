from typing import Literal

from pydantic import BaseModel, Field


class ParsedAddress(BaseModel):
    tipo_logradouro: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    sem_numero: bool = False
    complemento: str | None = None
    bairro: str | None = None
    localidade: str | None = None
    uf: str | None = None
    cep: str | None = None


class AddressCandidate(BaseModel):
    id: str
    raw_text: str
    cleaned: str
    confidence: float
    parsed: ParsedAddress | None = None


class CnefeMunicipio(BaseModel):
    cod_ibge: str
    nome: str | None = None
    uf: str | None = None
    lat: float
    lon: float
    raio_m: int
    n_ceps: int


class CnefeCep(BaseModel):
    cep: str
    lat: float
    lon: float
    raio_m: int
    generico: bool = False
    n_enderecos: int = 0
    logradouro: str | None = None
    localidade: str | None = None
    cod_ibge: str | None = None
    municipio: CnefeMunicipio | None = None


class CnefeStatus(BaseModel):
    disponivel: bool
    fonte: str | None = None
    gerado_em: str | None = None
    n_ceps: int = 0
    n_municipios: int = 0
    caminho: str | None = None


class CepInfo(BaseModel):
    cep: str
    logradouro: str | None = None
    bairro: str | None = None
    localidade: str | None = None
    uf: str | None = None
    ibge: str | None = None
    generico: bool = False
    source: str = "viacep"


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
    layer: str | None = None
    accuracy: str | None = None
    match_type: str | None = None
    street: str | None = None
    housenumber: str | None = None
    neighbourhood: str | None = None
    locality: str | None = None
    localadmin: str | None = None
    county: str | None = None
    region_a: str | None = None
    postalcode: str | None = None


ResolveStatus = Literal[
    "verificado", "provavel", "aproximado", "divergente", "nao_encontrado", "nao_verificado"
]


class ValidationCheck(BaseModel):
    nome: str
    ok: bool
    detalhe: str | None = None


class ResolvedAddress(BaseModel):
    id: str
    status: ResolveStatus
    label: str
    lat: float | None = None
    lon: float | None = None
    parsed: ParsedAddress | None = None
    cep_info: CepInfo | None = None
    cnefe: CnefeCep | None = None
    hit: GeocodeHit | None = None
    alternatives: list[GeocodeHit] = []
    checks: list[ValidationCheck] = []
    avisos: list[str] = []
    etapa: str | None = None


class ResolveRequest(BaseModel):
    text: str
    id: str | None = None
    origin_lat: float | None = None
    origin_lon: float | None = None


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
