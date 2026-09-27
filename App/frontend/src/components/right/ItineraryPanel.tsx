import { useEffect, useRef } from "react";
import { postJson } from "../../api/client";
import { vehicleColor } from "../../lib/fleet";
import { useAppStore } from "../../store/useAppStore";
import type { FleetPlan } from "../../types";

function fmtDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}min` : `${m}min`;
}

function fmtKm(meters: number): string {
  return `${(meters / 1000).toFixed(1).replace(".", ",")} km`;
}

function useOpenUrl() {
  const setError = useAppStore((s) => s.setError);
  return async (url: string) => {
    try {
      await postJson("/api/open-url", { url });
    } catch (e) {
      setError((e as Error).message);
    }
  };
}

function EtaControls() {
  const departureTime = useAppStore((s) => s.departureTime);
  const stopMinutes = useAppStore((s) => s.stopMinutes);
  const setDepartureTime = useAppStore((s) => s.setDepartureTime);
  const setStopMinutes = useAppStore((s) => s.setStopMinutes);

  const timer = useRef<number>();
  // O painel monta logo depois de cada cálculo: recalcular na montagem repetiria a
  // rota inteira (traçados do ORS e, na frota, o LKH) sem nada ter mudado.
  const last = useRef({ departureTime, stopMinutes });
  useEffect(() => {
    if (
      last.current.departureTime === departureTime &&
      last.current.stopMinutes === stopMinutes
    ) {
      return;
    }
    last.current = { departureTime, stopMinutes };
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const { plan, fleet, solve } = useAppStore.getState();
      if (plan || fleet) void solve();
    }, 600);
    return () => window.clearTimeout(timer.current);
  }, [departureTime, stopMinutes]);

  return (
    <div className="eta-controls">
      <label>
        <span>Hora de saída</span>
        <input
          type="time"
          value={departureTime}
          onChange={(e) => setDepartureTime(e.target.value)}
        />
      </label>
      <label>
        <span>Min. por parada</span>
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
  const open = useOpenUrl();
  if (!plan) return null;

  return (
    <>
      {plan.gmaps_urls.map((url, i) => (
        <button key={i} className="btn-primary grow" onClick={() => void open(url)}>
          {plan.gmaps_urls.length === 1
            ? "Abrir rota no Google Maps"
            : `Abrir no Google Maps (parte ${i + 1}/${plan.gmaps_urls.length})`}
        </button>
      ))}
    </>
  );
}

/** O itinerário com 2+ veículos: totais da frota e uma seção por veículo, cada uma
 * com a cor dele no mapa e seus próprios links do Google Maps (um por motorista). */
function FleetItinerary({ fleet }: { fleet: FleetPlan }) {
  const origin = useAppStore((s) => s.origin);
  const optimizeBy = useAppStore((s) => s.optimizeBy);
  const open = useOpenUrl();

  return (
    <>
      {fleet.warnings.map((w, i) => (
        <p className="warning" key={i}>⚠ {w}</p>
      ))}

      <div className="totals">
        <div>
          <strong>{fmtKm(fleet.total_distance_m)}</strong>
          <small>soma da frota</small>
        </div>
        <div>
          <strong>{fmtDuration(fleet.driving_duration_s)}</strong>
          <small>dirigindo (soma)</small>
        </div>
        <div>
          <strong>{fleet.last_return_eta}</strong>
          <small>último retorno</small>
        </div>
      </div>
      <p className="fleet-criterion">
        {optimizeBy === "duration"
          ? "Otimizado para o último veículo voltar o mais cedo possível."
          : "Otimizado para a menor soma de quilômetros da frota."}
      </p>

      <div className="it-list">
        <div className="it-row it-item origin">
          <span className="dot origin-dot">P</span>
          <span className="it-label" title={origin?.label}>
            {origin?.label ?? "Origem"}
          </span>
          <span className="it-time soft">saída</span>
          <span className="it-time">{fleet.departure_time}</span>
        </div>

        {fleet.routes.map((r) => {
          const color = vehicleColor(r.vehicle);
          return (
            <section className="fleet-route" key={r.vehicle}>
              <div className="fleet-route-head">
                <span className="dot" style={{ background: color }}>
                  {r.vehicle}
                </span>
                <div className="fleet-route-title">
                  <strong>Veículo {r.vehicle}</strong>
                  <small>
                    {r.ordered_stops.length}{" "}
                    {r.ordered_stops.length === 1 ? "parada" : "paradas"} ·{" "}
                    {fmtKm(r.total_distance_m)} · volta {r.return_eta}
                  </small>
                </div>
                {r.gmaps_urls.map((url, i) => (
                  <button
                    key={i}
                    className="fleet-maps"
                    title="Abrir a rota deste veículo no Google Maps"
                    onClick={() => void open(url)}
                  >
                    {r.gmaps_urls.length === 1 ? "Maps" : `Maps ${i + 1}/${r.gmaps_urls.length}`}
                  </button>
                ))}
              </div>
              {r.ordered_stops.map((ps) => (
                <div className="it-row it-item" key={ps.stop.id}>
                  <span className="order-dot" style={{ color, borderColor: color }}>
                    {ps.order}
                  </span>
                  <span className="it-label" title={ps.stop.label}>{ps.stop.label}</span>
                  <span className="it-time">{ps.eta}</span>
                  <span className="it-time soft">{ps.departs}</span>
                </div>
              ))}
            </section>
          );
        })}
      </div>
    </>
  );
}

export default function ItineraryPanel() {
  const plan = useAppStore((s) => s.plan);
  const fleet = useAppStore((s) => s.fleet);
  const origin = useAppStore((s) => s.origin);
  const setConfirmReset = useAppStore((s) => s.setConfirmReset);
  const stops = useAppStore((s) => s.stops);

  return (
    <div className="view">
      <EtaControls />

      {!plan && !fleet && (
        <p className="it-empty">
          Adicione o ponto de partida e as paradas, depois clique em “Calcular rota”
          para ver a ordem otimizada e os horários.
        </p>
      )}

      {plan && (
        <>
          {plan.warnings.map((w, i) => (
            <p className="warning" key={i}>⚠ {w}</p>
          ))}

          <div className="totals">
            <div>
              <strong>{fmtKm(plan.total_distance_m)}</strong>
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

          <div className="it-row it-head">
            <span>#</span>
            <span>Endereço</span>
            <span className="it-time soft">Chegada</span>
            <span className="it-time soft">Saída</span>
          </div>

          <div className="it-list">
            <div className="it-row it-item origin">
              <span className="dot origin-dot">P</span>
              <span className="it-label" title={origin?.label}>
                {origin?.label ?? "Origem"}
              </span>
              <span className="it-time soft">—</span>
              <span className="it-time">{plan.departure_time}</span>
            </div>
            {plan.ordered_stops.map((ps) => (
              <div className="it-row it-item" key={ps.stop.id}>
                <span className="order-dot">{ps.order}</span>
                <span className="it-label" title={ps.stop.label}>{ps.stop.label}</span>
                <span className="it-time">{ps.eta}</span>
                <span className="it-time soft">{ps.departs}</span>
              </div>
            ))}
            <div className="it-row it-item origin">
              <span className="dot origin-dot" />
              <span className="it-label">Retorno à origem</span>
              <span className="it-time">{plan.return_eta}</span>
              <span className="it-time soft">—</span>
            </div>
          </div>
        </>
      )}

      {fleet && <FleetItinerary fleet={fleet} />}

      <div className="panel-foot">
        <GmapsButtons />
        <button
          className="btn-ghost"
          disabled={!origin && stops.length === 0 && !plan && !fleet}
          onClick={() => setConfirmReset(true)}
        >
          Limpar tudo
        </button>
      </div>
    </div>
  );
}
