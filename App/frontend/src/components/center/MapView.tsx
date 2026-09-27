import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import {
  MapContainer,
  Marker,
  Polyline,
  TileLayer,
  ZoomControl,
  useMap,
  useMapEvents,
} from "react-leaflet";
import { vehicleColor } from "../../lib/fleet";
import { INITIAL_CENTER, INITIAL_ZOOM, useAppStore } from "../../store/useAppStore";

const ROUTE_COLOR = "#A51C30";

/** Uma linha desenhada no mapa: a rota de um veículo, com ou sem traçado real. */
interface DrawnRoute {
  key: string;
  color: string;
  positions: [number, number][];
  /** Sem traçado do ORS: liga os pontos em linha reta, tracejada. */
  straight: boolean;
}

/** O painel flutuante cobre os 440px da esquerda (mais 16px de margem de cada
 * lado): o enquadramento da rota tem de desviar dele, senão as primeiras paradas
 * ficam escondidas atrás do painel. */
const FIT_PADDING = {
  paddingTopLeft: [488, 40] as [number, number],
  paddingBottomRight: [40, 60] as [number, number],
};

interface ContextMenuState {
  x: number;
  y: number;
  lat: number;
  lng: number;
}

function pinIcon(content: string, kind: "origin" | "stop", color?: string) {
  const style = color ? ` style="background:${color}"` : "";
  return L.divIcon({
    className: "",
    html: `<div class="pin pin-${kind}"${style}>${content}</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
}

function MapEvents({
  onContextMenu,
  onCloseMenu,
}: {
  onContextMenu: (m: ContextMenuState) => void;
  onCloseMenu: () => void;
}) {
  const setMapCenter = useAppStore((s) => s.setMapCenter);

  useMapEvents({
    click() {
      onCloseMenu();
    },
    contextmenu(e) {
      e.originalEvent.preventDefault();
      onContextMenu({
        x: e.containerPoint.x,
        y: e.containerPoint.y,
        lat: e.latlng.lat,
        lng: e.latlng.lng,
      });
    },
    movestart() {
      onCloseMenu();
    },
    zoomstart() {
      onCloseMenu();
    },
    moveend(e) {
      const c = e.target.getCenter();
      setMapCenter([c.lat, c.lng]);
    },
  });
  return null;
}

function FlyTo() {
  const map = useMap();
  const flyTarget = useAppStore((s) => s.flyTarget);
  const setFlyTarget = useAppStore((s) => s.setFlyTarget);

  useEffect(() => {
    if (flyTarget) {
      map.flyTo(flyTarget, Math.max(map.getZoom(), 14));
      setFlyTarget(null);
    }
  }, [flyTarget, map, setFlyTarget]);
  return null;
}

function FitRoute() {
  const map = useMap();
  const plan = useAppStore((s) => s.plan);
  const fleet = useAppStore((s) => s.fleet);

  useEffect(() => {
    if (plan?.geometry && plan.geometry.length > 1) {
      map.fitBounds(L.latLngBounds(plan.geometry), FIT_PADDING);
    }
  }, [plan, map]);

  useEffect(() => {
    const pts = fleet?.routes.flatMap((r) => r.geometry ?? []) ?? [];
    if (pts.length > 1) map.fitBounds(L.latLngBounds(pts), FIT_PADDING);
  }, [fleet, map]);
  return null;
}

export default function MapView() {
  const origin = useAppStore((s) => s.origin);
  const stops = useAppStore((s) => s.stops);
  const plan = useAppStore((s) => s.plan);
  const fleet = useAppStore((s) => s.fleet);
  const moveOrigin = useAppStore((s) => s.moveOrigin);
  const moveStopPosition = useAppStore((s) => s.moveStopPosition);
  const addStopAt = useAppStore((s) => s.addStopAt);
  const setOriginAt = useAppStore((s) => s.setOriginAt);

  const [menu, setMenu] = useState<ContextMenuState | null>(null);

  // Número e cor de cada pino. Na frota, o número é a ordem dentro da rota do
  // veículo e a cor diz qual veículo passa ali.
  const pinById = useMemo(() => {
    const map = new Map<string, { order: number; color?: string }>();
    plan?.ordered_stops.forEach((ps) => map.set(ps.stop.id, { order: ps.order }));
    fleet?.routes.forEach((r) =>
      r.ordered_stops.forEach((ps) =>
        map.set(ps.stop.id, { order: ps.order, color: vehicleColor(r.vehicle) }),
      ),
    );
    return map;
  }, [plan, fleet]);

  const routes = useMemo<DrawnRoute[]>(() => {
    const drawn = (
      key: string,
      color: string,
      geometry: [number, number][] | null,
      stopsInOrder: { lat: number; lon: number }[],
    ): DrawnRoute | null => {
      if (geometry) return { key, color, positions: geometry, straight: false };
      if (!origin) return null;
      const home: [number, number] = [origin.lat, origin.lon];
      const pts = stopsInOrder.map((p) => [p.lat, p.lon] as [number, number]);
      return { key, color, positions: [home, ...pts, home], straight: true };
    };
    const out: (DrawnRoute | null)[] = [];
    if (plan) {
      out.push(drawn("plan", ROUTE_COLOR, plan.geometry, plan.ordered_stops.map((ps) => ps.stop)));
    }
    fleet?.routes.forEach((r) =>
      out.push(
        drawn(
          `v${r.vehicle}`,
          vehicleColor(r.vehicle),
          r.geometry,
          r.ordered_stops.map((ps) => ps.stop),
        ),
      ),
    );
    return out.filter((r): r is DrawnRoute => r !== null);
  }, [plan, fleet, origin]);

  return (
    <>
      <MapContainer
        center={INITIAL_CENTER}
        zoom={INITIAL_ZOOM}
        className="map"
        zoomControl={false}
      >
        <ZoomControl position="bottomright" />
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />
        <MapEvents onContextMenu={setMenu} onCloseMenu={() => setMenu(null)} />
        <FlyTo />
        <FitRoute />

        {origin && (
          <Marker
            position={[origin.lat, origin.lon]}
            icon={pinIcon("P", "origin")}
            draggable
            eventHandlers={{
              dragend: (e) => {
                const p = e.target.getLatLng();
                void moveOrigin(p.lat, p.lng);
              },
            }}
          />
        )}

        {stops.map((s, i) => (
          <Marker
            key={s.id}
            position={[s.lat, s.lon]}
            icon={pinIcon(
              String(pinById.get(s.id)?.order ?? i + 1),
              "stop",
              pinById.get(s.id)?.color,
            )}
            draggable
            eventHandlers={{
              dragend: (e) => {
                const p = e.target.getLatLng();
                void moveStopPosition(s.id, p.lat, p.lng);
              },
            }}
          />
        ))}

        {/* Contornos antes das linhas: onde duas rotas se sobrepõem (perto da
            partida), o contorno de uma não pode apagar a cor da outra. */}
        {routes.map((r) => (
          <Polyline
            key={`${r.key}-halo`}
            positions={r.positions}
            pathOptions={{
              color: "#fff",
              weight: r.straight ? 8 : 9,
              opacity: 0.9,
              lineJoin: "round",
            }}
          />
        ))}
        {routes.map((r) => (
          <Polyline
            key={r.key}
            positions={r.positions}
            pathOptions={
              r.straight
                ? { color: r.color, weight: 4, opacity: 0.85, dashArray: "8 8" }
                : { color: r.color, weight: 5, opacity: 0.85, lineJoin: "round" }
            }
          />
        ))}
      </MapContainer>

      {menu && (
        <div className="ctx-menu" style={{ left: menu.x, top: menu.y }}>
          <button
            disabled={!origin}
            title={origin ? undefined : "Defina o ponto de partida antes de adicionar paradas"}
            onClick={() => {
              void addStopAt(menu.lat, menu.lng);
              setMenu(null);
            }}
          >
            <span className="dot stop-dot">+</span> Adicionar parada aqui
          </button>
          <button
            onClick={() => {
              void setOriginAt(menu.lat, menu.lng);
              setMenu(null);
            }}
          >
            <span className="dot origin-dot">P</span> Definir partida aqui
          </button>
        </div>
      )}
    </>
  );
}
