import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { newStopId, useAppStore } from "../../store/useAppStore";
import type { GeocodeHit } from "../../types";

export default function AddressSearch() {
  const addStop = useAppStore((s) => s.addStop);
  const setOrigin = useAppStore((s) => s.setOrigin);
  const setFlyTarget = useAppStore((s) => s.setFlyTarget);
  const mapCenter = useAppStore((s) => s.mapCenter);
  const setError = useAppStore((s) => s.setError);

  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<GeocodeHit[]>([]);
  const [loading, setLoading] = useState(false);
  const timer = useRef<number>();

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (query.trim().length < 2) {
      setHits([]);
      return;
    }
    timer.current = window.setTimeout(async () => {
      setLoading(true);
      try {
        const results = await api<GeocodeHit[]>(
          `/api/geocode/autocomplete?text=${encodeURIComponent(query)}` +
            `&focus_lat=${mapCenter[0]}&focus_lon=${mapCenter[1]}`,
        );
        setHits(results);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => window.clearTimeout(timer.current);
  }, [query, mapCenter, setError]);

  const pick = (hit: GeocodeHit, asOrigin: boolean) => {
    const stop = { id: newStopId(), label: hit.label, lat: hit.lat, lon: hit.lon };
    if (asOrigin) setOrigin(stop);
    else addStop(stop);
    setFlyTarget([hit.lat, hit.lon]);
    setQuery("");
    setHits([]);
  };

  return (
    <section className="card">
      <div className="card-body search-box">
        <input
          type="text"
          value={query}
          placeholder="Buscar endereço (ex.: R. Alfredo Guedes ou só o nome da rua)"
          onChange={(e) => setQuery(e.target.value)}
        />
        {loading && <small>Buscando...</small>}
        {hits.length > 0 && (
          <ul className="search-results">
            {hits.map((h, i) => (
              <li key={i}>
                <span className="hit-label" title={h.label}>{h.label}</span>
                <div className="hit-actions">
                  <button title="Adicionar como parada" onClick={() => pick(h, false)}>
                    + Parada
                  </button>
                  <button title="Definir como ponto de partida" onClick={() => pick(h, true)}>
                    Partida
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
