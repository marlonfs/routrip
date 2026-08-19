import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { badgeNumero, rotuloParada } from "../../lib/endereco";
import { newStopId, useAppStore } from "../../store/useAppStore";
import type { AddressOption } from "../../types";

/** Sem ponto de partida definido o foco é o centro do mapa, que pode estar longe de onde
 * o usuário quer. Dizer a distância é o que denuncia a rua homônima da cidade errada. */
function distancia(o: AddressOption): string | null {
  if (o.distancia_m == null || o.distancia_m < 2000) return null;
  return `a ${(o.distancia_m / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} km`;
}

export default function AddressSearch() {
  const addStop = useAppStore((s) => s.addStop);
  const origin = useAppStore((s) => s.origin);
  const setOrigin = useAppStore((s) => s.setOrigin);
  const setFlyTarget = useAppStore((s) => s.setFlyTarget);
  const mapCenter = useAppStore((s) => s.mapCenter);
  const setError = useAppStore((s) => s.setError);

  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<AddressOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [vazio, setVazio] = useState(false);
  const timer = useRef<number>();

  useEffect(() => {
    window.clearTimeout(timer.current);
    setVazio(false);
    if (query.trim().length < 3) {
      setHits([]);
      return;
    }
    const focus = origin ? [origin.lat, origin.lon] : mapCenter;
    timer.current = window.setTimeout(async () => {
      setLoading(true);
      try {
        const results = await api<AddressOption[]>(
          `/api/address/sugerir?texto=${encodeURIComponent(query)}` +
            `&focus_lat=${focus[0]}&focus_lon=${focus[1]}`,
        );
        setHits(results);
        setVazio(results.length === 0);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => window.clearTimeout(timer.current);
  }, [query, mapCenter, origin, setError]);

  const pick = (o: AddressOption, asOrigin: boolean) => {
    const label = rotuloParada(o, o.numero != null ? String(o.numero) : "");
    const stop = { id: newStopId(), label, lat: o.lat, lon: o.lon };
    if (asOrigin) setOrigin(stop);
    else addStop(stop);
    setFlyTarget([o.lat, o.lon]);
    setQuery("");
    setHits([]);
  };

  return (
    <section className="card">
      <div className="card-body search-box">
        <input
          type="text"
          value={query}
          placeholder="Buscar endereço (ex.: Alfredo Guedes 1500)"
          onChange={(e) => setQuery(e.target.value)}
        />
        {loading && <small>Buscando...</small>}
        {vazio && !loading && (
          <small className="muted">
            Nenhum endereço encontrado. Escreva a cidade junto para procurar fora da
            região do mapa.
          </small>
        )}
        {hits.length > 0 && (
          <ul className="search-results">
            {hits.map((o) => (
              <li key={o.id}>
                <span className="hit-label" title={o.label}>
                  {rotuloParada(o, o.numero != null ? String(o.numero) : "")}
                </span>
                <div className="hit-badges">
                  {o.confirmado ? (
                    <span className={badgeNumero(o).classe}>{badgeNumero(o).texto}</span>
                  ) : (
                    <span className="badge warn">não confirmado</span>
                  )}
                  {distancia(o) && <small className="muted">{distancia(o)}</small>}
                </div>
                <div className="hit-actions">
                  <button
                    title={
                      origin
                        ? "Adicionar como parada"
                        : "Defina o ponto de partida antes de adicionar paradas"
                    }
                    disabled={!origin}
                    onClick={() => pick(o, false)}
                  >
                    + Parada
                  </button>
                  <button title="Definir como ponto de partida" onClick={() => pick(o, true)}>
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
