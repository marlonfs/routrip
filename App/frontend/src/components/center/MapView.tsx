import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import {
  MapContainer,
  Marker,
  Polyline,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";
import { INITIAL_CENTER, INITIAL_ZOOM, useAppStore } from "../../store/useAppStore";

const ROUTE_COLOR = "#A51C30";

interface ContextMenuState {
  x: number;
  y: number;
  lat: number;
  lng: number;
}

function pinIcon(content: string, kind: "origin" | "stop") {
  return L.divIcon({
    className: "",
    html: `<div class="pin pin-${kind}">${content}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
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

  useEffect(() => {
    if (plan?.geometry && plan.geometry.length > 1) {
      map.fitBounds(L.latLngBounds(plan.geometry), { padding: [40, 40] });
    }
  }, [plan, map]);
  return null;
}

export default function MapView() {
  const origin = useAppStore((s) => s.origin);
  const stops = useAppStore((s) => s.stops);
  const plan = useAppStore((s) => s.plan);
  const moveOrigin = useAppStore((s) => s.moveOrigin);
  const moveStopPosition = useAppStore((s) => s.moveStopPosition);
  const addStopAt = useAppStore((s) => s.addStopAt);
  const setOriginAt = useAppStore((s) => s.setOriginAt);

  const [menu, setMenu] = useState<ContextMenuState | null>(null);

  const orderById = useMemo(() => {
    const map = new Map<string, number>();
    plan?.ordered_stops.forEach((ps) => map.set(ps.stop.id, ps.order));
    return map;
  }, [plan]);

  const fallbackLine = useMemo(() => {
    if (!plan || plan.geometry) return null;
    const pts: [number, number][] = plan.ordered_stops.map((ps) => [ps.stop.lat, ps.stop.lon]);
    if (!origin) return null;
    return [[origin.lat, origin.lon] as [number, number], ...pts, [origin.lat, origin.lon] as [number, number]];
  }, [plan, origin]);

  return (
    <>
      <MapContainer center={INITIAL_CENTER} zoom={INITIAL_ZOOM} className="map">
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
            icon={pinIcon(String(orderById.get(s.id) ?? i + 1), "stop")}
            draggable
            eventHandlers={{
              dragend: (e) => {
                const p = e.target.getLatLng();
                void moveStopPosition(s.id, p.lat, p.lng);
              },
            }}
          />
        ))}

        {plan?.geometry && (
          <Polyline positions={plan.geometry} pathOptions={{ color: ROUTE_COLOR, weight: 4, opacity: 0.85 }} />
        )}
        {fallbackLine && (
          <Polyline positions={fallbackLine} pathOptions={{ color: ROUTE_COLOR, weight: 3, dashArray: "8 8" }} />
        )}
      </MapContainer>

      {menu && (
        <div className="ctx-menu" style={{ left: menu.x, top: menu.y }}>
          <button
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
