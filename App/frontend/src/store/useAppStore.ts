import { create, type StoreApi } from "zustand";
import { api, postJson, putJson } from "../api/client";
import type {
  AddressCandidate,
  AppConfigResponse,
  GeocodeHit,
  OptimizeBy,
  ResolvedAddress,
  RoutePlan,
  SpreadsheetPreview,
  Stop,
} from "../types";

const SPREADSHEET_RE = /\.(csv|txt|xlsx|xlsm|xls)$/i;

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
  /** Uma proposta por candidato, na mesma ordem. Vem pronta da importação porque sai
   * da base local: o modal já abre com endereços que existem no cadastro do IBGE. */
  propostas: ResolvedAddress[];
  reviewOpen: boolean;
  importLoading: boolean;
  spreadsheet: SpreadsheetPreview | null;
  spreadsheetQueue: File[];

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
  requireOrigin: () => boolean;
  addStop: (s: Stop) => void;
  addStopAt: (lat: number, lon: number) => Promise<void>;
  removeStop: (id: string) => void;
  moveStopPosition: (id: string, lat: number, lon: number) => Promise<void>;
  moveOrigin: (lat: number, lon: number) => Promise<void>;

  importFiles: (files: File[]) => Promise<void>;
  addSpreadsheetLines: (lines: string[]) => Promise<void>;
  skipSpreadsheet: () => void;
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

type StoreSet = StoreApi<AppState>["setState"];
type StoreGet = StoreApi<AppState>["getState"];

/** Abre a próxima planilha da fila; sem planilhas pendentes, encerra a importação
 * levando tudo o que foi reunido para a revisão. */
async function advanceImport(set: StoreSet, get: StoreGet) {
  const [file, ...rest] = get().spreadsheetQueue;
  if (file) {
    set({ spreadsheetQueue: rest, spreadsheet: null, importLoading: true });
    const form = new FormData();
    form.append("file", file);
    try {
      const preview = await api<SpreadsheetPreview>("/api/spreadsheet/preview", {
        method: "POST",
        body: form,
      });
      set({ spreadsheet: preview, importLoading: false });
    } catch (e) {
      set({ error: (e as Error).message });
      await advanceImport(set, get);
    }
    return;
  }

  set({ spreadsheet: null, importLoading: false });
  if (get().candidates.length === 0) {
    set({
      error:
        "Nenhum endereço foi adicionado. Tente uma imagem mais nítida ou confira as colunas escolhidas na planilha.",
    });
    return;
  }
  set({ reviewOpen: true });
}

export const useAppStore = create<AppState>((set, get) => ({
  config: null,
  optimizeBy: "duration",
  departureTime: "08:00",
  stopMinutes: 10,

  origin: null,
  stops: [],

  candidates: [],
  propostas: [],
  reviewOpen: false,
  importLoading: false,
  spreadsheet: null,
  spreadsheetQueue: [],

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

  setOrigin: (s) => {
    if (!s && get().stops.length > 0) {
      set({ error: "Remova as paradas antes de limpar o ponto de partida." });
      return;
    }
    set({ origin: s, plan: null });
  },

  // O ponto de partida é o foco geográfico de toda geocodificação: sem ele, o
  // geocoder não tem como desempatar ruas homônimas em cidades diferentes.
  requireOrigin: () => {
    if (get().origin) return true;
    set({ error: "Defina o ponto de partida antes de adicionar paradas." });
    return false;
  },

  setOriginAt: async (lat, lon) => {
    set({
      origin: { id: "origin", label: `${lat.toFixed(5)}, ${lon.toFixed(5)}`, lat, lon },
      plan: null,
    });
    const label = await reverseLabel(lat, lon);
    const current = get().origin;
    if (current) set({ origin: { ...current, label } });
  },

  addStop: (s) => {
    if (!get().requireOrigin()) return;
    set((st) => ({ stops: [...st.stops, s], plan: null }));
  },

  addStopAt: async (lat, lon) => {
    if (!get().requireOrigin()) return;
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

  importFiles: async (files) => {
    if (!get().requireOrigin()) return;
    const spreadsheets = files.filter((f) => SPREADSHEET_RE.test(f.name));
    const documents = files.filter((f) => !SPREADSHEET_RE.test(f.name));
    set({
      importLoading: true,
      error: null,
      candidates: [],
      propostas: [],
      reviewOpen: false,
      spreadsheet: null,
      spreadsheetQueue: spreadsheets,
    });

    if (documents.length > 0) {
      const form = new FormData();
      documents.forEach((f) => form.append("files", f));
      try {
        const result = await api<{
          text: string;
          candidates: AddressCandidate[];
          propostas: ResolvedAddress[];
        }>("/api/ocr", { method: "POST", body: form });
        set({ candidates: result.candidates, propostas: result.propostas });
      } catch (e) {
        set({ error: (e as Error).message, importLoading: false, spreadsheetQueue: [] });
        return;
      }
    }
    await advanceImport(set, get);
  },

  addSpreadsheetLines: async (lines) => {
    if (!get().requireOrigin()) return;
    set({ spreadsheet: null, importLoading: true });
    try {
      const result = await postJson<{
        candidates: AddressCandidate[];
        propostas: ResolvedAddress[];
      }>("/api/addresses/parse", { lines });
      set((st) => ({
        candidates: [...st.candidates, ...result.candidates],
        propostas: [...st.propostas, ...result.propostas],
      }));
    } catch (e) {
      set({ error: (e as Error).message });
    }
    await advanceImport(set, get);
  },

  skipSpreadsheet: () => {
    void advanceImport(set, get);
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
