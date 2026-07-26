import { useState } from "react";
import { api } from "../../api/client";
import { newStopId, useAppStore } from "../../store/useAppStore";
import type { GeocodeHit } from "../../types";

interface ReviewItem {
  id: string;
  text: string;
  selected: boolean;
  status: "" | "ok" | "erro" | "não encontrado";
}

export default function OcrReviewModal() {
  const candidates = useAppStore((s) => s.candidates);
  const setReviewOpen = useAppStore((s) => s.setReviewOpen);
  const addStop = useAppStore((s) => s.addStop);

  const [items, setItems] = useState<ReviewItem[]>(() =>
    candidates.map((c) => ({ id: c.id, text: c.cleaned, selected: true, status: "" })),
  );
  const [busy, setBusy] = useState(false);

  const update = (id: string, changes: Partial<ReviewItem>) =>
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...changes } : it)));

  const geocodeSelected = async () => {
    setBusy(true);
    let failures = 0;
    for (const item of items.filter((it) => it.selected && it.status !== "ok")) {
      try {
        const hits = await api<GeocodeHit[]>(
          `/api/geocode/search?text=${encodeURIComponent(item.text)}`,
        );
        if (hits.length > 0) {
          const hit = hits[0];
          addStop({ id: newStopId(), label: hit.label, lat: hit.lat, lon: hit.lon });
          update(item.id, { status: "ok" });
        } else {
          update(item.id, { status: "não encontrado" });
          failures++;
        }
      } catch {
        update(item.id, { status: "erro" });
        failures++;
      }
    }
    setBusy(false);
    if (failures === 0) setReviewOpen(false);
  };

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2>Endereços encontrados nas imagens</h2>
        <p className="muted">
          Revise, edite e selecione os endereços que devem entrar na rota.
        </p>
        <div className="review-list">
          {items.map((item) => (
            <div className="review-item" key={item.id}>
              <input
                type="checkbox"
                checked={item.selected}
                disabled={item.status === "ok"}
                onChange={(e) => update(item.id, { selected: e.target.checked })}
              />
              <input
                type="text"
                value={item.text}
                disabled={item.status === "ok"}
                onChange={(e) => update(item.id, { text: e.target.value, status: "" })}
              />
              {item.status && (
                <span className={item.status === "ok" ? "badge ok" : "badge warn"}>
                  {item.status}
                </span>
              )}
            </div>
          ))}
        </div>
        <div className="modal-actions">
          <button className="btn-secondary" onClick={() => setReviewOpen(false)}>
            Fechar
          </button>
          <button
            className="btn-primary"
            disabled={busy || items.every((it) => !it.selected || it.status === "ok")}
            onClick={() => void geocodeSelected()}
          >
            {busy ? "Geocodificando..." : "Geocodificar selecionados"}
          </button>
        </div>
      </div>
    </div>
  );
}
