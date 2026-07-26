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
}

export interface AddressCandidate {
  id: string;
  raw_text: string;
  cleaned: string;
  confidence: number;
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
}
