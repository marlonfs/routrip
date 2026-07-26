import { useEffect, useRef } from "react";
import { postJson } from "../../api/client";
import { useAppStore } from "../../store/useAppStore";

function fmtDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}min` : `${m}min`;
}

function EtaControls() {
  const departureTime = useAppStore((s) => s.departureTime);
  const stopMinutes = useAppStore((s) => s.stopMinutes);
  const setDepartureTime = useAppStore((s) => s.setDepartureTime);
  const setStopMinutes = useAppStore((s) => s.setStopMinutes);

  const timer = useRef<number>();
  useEffect(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const { plan, solve } = useAppStore.getState();
      if (plan) void solve();
    }, 600);
    return () => window.clearTimeout(timer.current);
  }, [departureTime, stopMinutes]);

  return (
    <div className="eta-controls">
      <label className="field">
        <span>Hora de saída</span>
        <input
          type="time"
          value={departureTime}
          onChange={(e) => setDepartureTime(e.target.value)}
        />
      </label>
      <label className="field">
        <span>Minutos por parada</span>
        <input
          type="number"
          min={0}
          max={240}
          value={stopMinutes}
          onChange={(e) => setStopMinutes(Math.max(0, Number(e.target.value) || 0))}
        />
      </label>
    </div>
  );
}

function GmapsButtons() {
  const plan = useAppStore((s) => s.plan);
  const setError = useAppStore((s) => s.setError);
  if (!plan) return null;

  const open = async (url: string) => {
    try {
      await postJson("/api/open-url", { url });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="gmaps-buttons">
      {plan.gmaps_urls.map((url, i) => (
        <button key={i} className="btn-primary full" onClick={() => void open(url)}>
          {plan.gmaps_urls.length === 1
            ? "Abrir rota no Google Maps"
            : `Abrir no Google Maps (parte ${i + 1}/${plan.gmaps_urls.length})`}
        </button>
      ))}
    </div>
  );
}

export default function ItineraryPanel() {
  const plan = useAppStore((s) => s.plan);
  const origin = useAppStore((s) => s.origin);

  return (
    <div className="itinerary">
      <EtaControls />
      {!plan && (
        <p className="muted">
          Adicione o ponto de partida e as paradas, depois clique em
          "Calcular rota" para ver a ordem otimizada e os horários.
        </p>
      )}
      {plan && (
        <>
          {plan.warnings.map((w, i) => (
            <p className="warning" key={i}>⚠ {w}</p>
          ))}
          <div className="itinerary-list">
            <div className="it-item origin">
              <span className="dot origin-dot" />
              <div className="it-info">
                <span className="it-label" title={origin?.label}>{origin?.label ?? "Origem"}</span>
                <small>Saída às {plan.departure_time}</small>
              </div>
            </div>
            {plan.ordered_stops.map((ps) => (
              <div className="it-item" key={ps.stop.id}>
                <span className="dot stop-dot">{ps.order}</span>
                <div className="it-info">
                  <span className="it-label" title={ps.stop.label}>{ps.stop.label}</span>
                  <small>
                    Chegada {ps.eta} · Saída {ps.departs}
                  </small>
                </div>
              </div>
            ))}
            <div className="it-item origin">
              <span className="dot origin-dot" />
              <div className="it-info">
                <span className="it-label">Retorno à origem</span>
                <small>Chegada às {plan.return_eta}</small>
              </div>
            </div>
          </div>
          <div className="totals">
            <div>
              <strong>{(plan.total_distance_m / 1000).toFixed(1)} km</strong>
              <small>distância total</small>
            </div>
            <div>
              <strong>{fmtDuration(plan.driving_duration_s)}</strong>
              <small>dirigindo</small>
            </div>
            <div>
              <strong>{fmtDuration(plan.total_duration_s)}</strong>
              <small>tempo total</small>
            </div>
          </div>
          <GmapsButtons />
        </>
      )}
    </div>
  );
}
