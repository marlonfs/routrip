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


NumeroStatus = Literal[
    # a coordenada é a que o IBGE registrou nesta casa
    "exato",
    # o número não está cadastrado; a posição saiu dos dois cadastrados que o cercam
    "vizinho",
    # o número está fora do intervalo cadastrado na rua
    "fora",
    # base antiga, sem numeração: só se sabe que o número cai entre num_min e num_max
    "faixa",
    # a rua existe mas nenhuma casa dela tem número no cadastro (comum na zona rural)
    "sem_numeracao",
    # não foi pedido número nenhum
    "sem_numero",
]


class CnefeLogradouro(BaseModel):
    cod_ibge: str
    nome: str
    tipo: str | None = None
    label: str
    lat: float
    lon: float
    raio_m: int
    n_enderecos: int = 0
    cep: str | None = None
    num_min: int | None = None
    num_max: int | None = None
    numero: int | None = None
    numero_confirmado: bool = False
    numero_status: NumeroStatus = "sem_numero"
    # Os dois cadastrados que cercam o número procurado. É o que deixa o usuário julgar
    # a posição: entre 450 e 460 é a casa certa, entre 100 e 890 é o meio da rua.
    num_antes: int | None = None
    num_depois: int | None = None
    n_numeros: int = 0
    # O IBGE marcou a coordenada na face da quadra, não na porta.
    coordenada_aproximada: bool = False
    distancia_m: float | None = None
    similaridade: float = 1.0
    municipio: CnefeMunicipio | None = None


class CnefeStatus(BaseModel):
    disponivel: bool
    fonte: str | None = None
    gerado_em: str | None = None
    n_ceps: int = 0
    n_municipios: int = 0
    n_logradouros: int = 0
    n_numeros: int = 0
    busca_por_rua: bool = False
    numeracao: bool = False
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


class AddressOption(BaseModel):
    """Um endereço que o usuário pode escolher. `fonte="cnefe"` existe no cadastro do
    IBGE; `fonte="ors"` é palpite de geocoder e só aparece quando o CNEFE não achou
    nada — daí `confirmado` nunca ser verdadeiro nesse caso."""

    id: str
    fonte: Literal["cnefe", "ors"]
    confirmado: bool
    label: str
    lat: float
    lon: float
    logradouro: str | None = None
    numero: int | None = None
    numero_confirmado: bool = False
    numero_status: NumeroStatus = "sem_numero"
    num_antes: int | None = None
    num_depois: int | None = None
    num_min: int | None = None
    num_max: int | None = None
    municipio: str | None = None
    uf: str | None = None
    cep: str | None = None
    # Do foco do mapa até a rua. Só a busca manual preenche; o modal de importação não
    # tem foco nenhum.
    distancia_m: float | None = None
    similaridade: float = 1.0


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
    options: list[AddressOption] = []
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
