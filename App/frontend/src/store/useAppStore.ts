import { create } from "zustand";
import { api, postJson, putJson } from "../api/client";
import type {
  AddressCandidate,
  AppConfigResponse,
  GeocodeHit,
  OptimizeBy,
  RoutePlan,
  Stop,
} from "../types";

// ESALQ/USP, Piracicaba-SP — centro inicial do mapa
export const INITIAL_CENTER: [number, number] = [-22.7089, -47.6328];
export const INITIAL_ZOOM = 15;

let idCounter = 0;
export const newStopId = () =>
  `s${Date.now().toString(36)}${(idCounter++).toString(36)}`;

interface AppState {
  config: AppConfigResponse | null;
  optimizeBy: OptimizeBy;
  departureTime: string;
  stopMinutes: number;

  origin: Stop | null;
  stops: Stop[];

  candidates: AddressCandidate[];
  reviewOpen: boolean;
  ocrLoading: boolean;

  plan: RoutePlan | null;
  solving: boolean;

  mapCenter: [number, number];
  flyTarget: [number, number] | null;
  error: string | null;

  loadConfig: () => Promise<void>;
  saveSettings: (update: Partial<AppConfigResponse> & { ors_api_key?: string }) => Promise<void>;
  setDepartureTime: (v: string) => void;
  setStopMinutes: (v: number) => void;
  setOptimizeBy: (v: OptimizeBy) => void;

  setOrigin: (s: Stop | null) => void;
  setOriginAt: (lat: number, lon: number) => Promise<void>;
  addStop: (s: Stop) => void;
  addStopAt: (lat: number, lon: number) => Promise<void>;
  removeStop: (id: string) => void;
  moveStopPosition: (id: string, lat: number, lon: number) => Promise<void>;
  moveOrigin: (lat: number, lon: number) => Promise<void>;

  runOcr: (files: File[]) => Promise<void>;
  setReviewOpen: (open: boolean) => void;

  solve: () => Promise<void>;
  invalidatePlan: () => void;

  setMapCenter: (c: [number, number]) => void;
  setFlyTarget: (c: [number, number] | null) => void;
  setError: (e: string | null) => void;
}

async function reverseLabel(lat: number, lon: number): Promise<string> {
  try {
    const hit = await api<GeocodeHit | null>(
      `/api/geocode/reverse?lat=${lat}&lon=${lon}`,
    );
    if (hit?.label) return hit.label;
  } catch {
    // sem chave ou falha de rede: usa coordenadas como rótulo
  }
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

export const useAppStore = create<AppState>((set, get) => ({
  config: null,
  optimizeBy: "duration",
  departureTime: "08:00",
  stopMinutes: 10,

  origin: null,
  stops: [],

  candidates: [],
  reviewOpen: false,
  ocrLoading: false,

  plan: null,
  solving: false,

  mapCenter: INITIAL_CENTER,
  flyTarget: null,
  error: null,

  loadConfig: async () => {
    try {
      const config = await api<AppConfigResponse>("/api/config");
      set({
        config,
        optimizeBy: config.optimize_by,
        departureTime: config.departure_time,
        stopMinutes: config.stop_minutes,
      });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  saveSettings: async (update) => {
    try {
      const config = await putJson<AppConfigResponse>("/api/config", update);
      set({ config, optimizeBy: config.optimize_by });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  setDepartureTime: (v) => set({ departureTime: v }),
  setStopMinutes: (v) => set({ stopMinutes: v }),
  setOptimizeBy: (v) => {
    set({ optimizeBy: v });
    void get().saveSettings({ optimize_by: v });
  },

  setOrigin: (s) => set({ origin: s, plan: null }),

  setOriginAt: async (lat, lon) => {
    set({
      origin: { id: "origin", label: `${lat.toFixed(5)}, ${lon.toFixed(5)}`, lat, lon },
      plan: null,
    });
    const label = await reverseLabel(lat, lon);
    const current = get().origin;
    if (current) set({ origin: { ...current, label } });
  },

  addStop: (s) => set((st) => ({ stops: [...st.stops, s], plan: null })),

  addStopAt: async (lat, lon) => {
    const id = newStopId();
    set((st) => ({
      stops: [...st.stops, { id, label: `${lat.toFixed(5)}, ${lon.toFixed(5)}`, lat, lon }],
      plan: null,
    }));
    const label = await reverseLabel(lat, lon);
    set((st) => ({
      stops: st.stops.map((s) => (s.id === id ? { ...s, label } : s)),
    }));
  },
  removeStop: (id) =>
    set((st) => ({ stops: st.stops.filter((s) => s.id !== id), plan: null })),

  moveStopPosition: async (id, lat, lon) => {
    set((st) => ({
      stops: st.stops.map((s) => (s.id === id ? { ...s, lat, lon } : s)),
      plan: null,
    }));
    const label = await reverseLabel(lat, lon);
    set((st) => ({
      stops: st.stops.map((s) => (s.id === id ? { ...s, label } : s)),
    }));
  },

  moveOrigin: async (lat, lon) => {
    const origin = get().origin;
    if (!origin) return;
    set({ origin: { ...origin, lat, lon }, plan: null });
    const label = await reverseLabel(lat, lon);
    const current = get().origin;
    if (current) set({ origin: { ...current, label } });
  },

  runOcr: async (files) => {
    set({ ocrLoading: true, error: null });
    try {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      const result = await api<{ text: string; candidates: AddressCandidate[] }>(
        "/api/ocr",
        { method: "POST", body: form },
      );
      if (result.candidates.length === 0) {
        set({
          ocrLoading: false,
          error: "Nenhum endereço foi identificado nos arquivos. Tente uma foto mais nítida ou confira a planilha.",
        });
        return;
      }
      set({ candidates: result.candidates, reviewOpen: true, ocrLoading: false });
    } catch (e) {
      set({ error: (e as Error).message, ocrLoading: false });
    }
  },

  setReviewOpen: (open) => set({ reviewOpen: open }),

  solve: async () => {
    const { origin, stops, optimizeBy, departureTime, stopMinutes } = get();
    if (!origin) {
      set({ error: "Defina o ponto de partida antes de calcular a rota." });
      return;
    }
    if (stops.length === 0) {
      set({ error: "Adicione pelo menos uma parada." });
      return;
    }
    set({ solving: true, error: null });
    try {
      const plan = await postJson<RoutePlan>("/api/route/solve", {
        origin,
        stops,
        optimize_by: optimizeBy,
        departure_time: departureTime,
        stop_minutes: stopMinutes,
        want_geometry: true,
      });
      set({ plan, solving: false });
    } catch (e) {
      set({ error: (e as Error).message, solving: false });
    }
  },

  invalidatePlan: () => set({ plan: null }),

  setMapCenter: (c) => set({ mapCenter: c }),
  setFlyTarget: (c) => set({ flyTarget: c }),
  setError: (e) => set({ error: e }),
}));
