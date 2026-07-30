export interface Stop {
  id: string;
  label: string;
  lat: number;
  lon: number;
}

export interface GeocodeHit {
  label: string;
  lat: number;
  lon: number;
  confidence: number;
  layer?: string | null;
  accuracy?: string | null;
  match_type?: string | null;
  street?: string | null;
  housenumber?: string | null;
  neighbourhood?: string | null;
  locality?: string | null;
  localadmin?: string | null;
  county?: string | null;
  region_a?: string | null;
  postalcode?: string | null;
}

export interface ParsedAddress {
  tipo_logradouro: string | null;
  logradouro: string | null;
  numero: string | null;
  sem_numero: boolean;
  complemento: string | null;
  bairro: string | null;
  localidade: string | null;
  uf: string | null;
  cep: string | null;
}

export interface AddressCandidate {
  id: string;
  raw_text: string;
  cleaned: string;
  confidence: number;
  parsed?: ParsedAddress | null;
}

export type ResolveStatus =
  | "verificado"
  | "provavel"
  | "aproximado"
  | "divergente"
  | "nao_encontrado"
  | "nao_verificado";

export interface ValidationCheck {
  nome: string;
  ok: boolean;
  detalhe: string | null;
}

export interface CepInfo {
  cep: string;
  logradouro: string | null;
  bairro: string | null;
  localidade: string | null;
  uf: string | null;
  ibge: string | null;
  generico: boolean;
  source: string;
}

export interface ResolvedAddress {
  id: string;
  status: ResolveStatus;
  label: string;
  lat: number | null;
  lon: number | null;
  parsed: ParsedAddress | null;
  cep_info: CepInfo | null;
  hit: GeocodeHit | null;
  alternatives: GeocodeHit[];
  checks: ValidationCheck[];
  avisos: string[];
  etapa: string | null;
}

export interface CnefeStatus {
  disponivel: boolean;
  fonte: string | null;
  gerado_em: string | null;
  n_ceps: number;
  n_municipios: number;
  caminho: string | null;
}

export interface SpreadsheetSheet {
  name: string;
  rows: string[][];
  total_rows: number;
  truncated: boolean;
}

export interface SpreadsheetPreview {
  filename: string;
  sheets: SpreadsheetSheet[];
}

export interface PlannedStop {
  stop: Stop;
  order: number;
  eta: string;
  departs: string;
}

export interface RoutePlan {
  ordered_stops: PlannedStop[];
  departure_time: string;
  return_eta: string;
  total_duration_s: number;
  total_distance_m: number;
  driving_duration_s: number;
  geometry: [number, number][] | null;
  gmaps_urls: string[];
  warnings: string[];
}

export type OptimizeBy = "duration" | "distance";

export interface AppConfigResponse {
  ors_api_key: string;
  ors_key_set: boolean;
  optimize_by: OptimizeBy;
  departure_time: string;
  stop_minutes: number;
  validate_addresses: boolean;
  ocr_preprocess: boolean;
  ocr_psm_mode: "auto" | "6" | "11";
}
