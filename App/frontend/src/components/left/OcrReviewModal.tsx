import { useRef, useState } from "react";
import { api } from "../../api/client";
import { newStopId, useAppStore } from "../../store/useAppStore";
import type { GeocodeHit, ResolveStatus, ResolvedAddress } from "../../types";

interface ReviewItem {
  id: string;
  text: string;
  selected: boolean;
  added: boolean;
  erro?: string;
  resolved?: ResolvedAddress;
}

const ROTULO: Record<ResolveStatus, string> = {
  verificado: "verificado",
  provavel: "provável",
  aproximado: "aproximado",
  divergente: "divergente",
  nao_encontrado: "não encontrado",
  nao_verificado: "não verificado",
};

const AVISO: Record<string, string> = {
  cep_logradouro_divergente: "a rua lida não bate com a do CEP",
  cep_inexistente: "CEP não existe",
  cep_nao_verificado: "não foi possível consultar o CEP",
  cep_fora_da_base: "CEP ausente na base do IBGE",
  cep_generico: "CEP genérico, cobre a cidade inteira",
};

// Verde entra sozinho na rota; amarelo e vermelho exigem confirmação do usuário.
const AUTOMATICO: ResolveStatus[] = ["verificado", "provavel"];

function badgeClass(status: ResolveStatus): string {
  if (status === "verificado") return "badge ok";
  if (status === "provavel") return "badge ok soft";
  if (status === "nao_encontrado") return "badge err";
  return "badge warn";
}

export default function OcrReviewModal() {
  const candidates = useAppStore((s) => s.candidates);
  const setReviewOpen = useAppStore((s) => s.setReviewOpen);
  const addStop = useAppStore((s) => s.addStop);
  const origin = useAppStore((s) => s.origin);

  const [items, setItems] = useState<ReviewItem[]>(() =>
    candidates.map((c) => ({ id: c.id, text: c.cleaned, selected: true, added: false })),
  );
  const [busy, setBusy] = useState(false);
  const [progresso, setProgresso] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const update = (id: string, changes: Partial<ReviewItem>) =>
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...changes } : it)));

  const aceitar = (item: ReviewItem, label: string, lat: number, lon: number) => {
    addStop({ id: newStopId(), label, lat, lon });
    update(item.id, { added: true, selected: false });
  };

  const resolver = async () => {
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setProgresso(0);

    const fila = items.filter((it) => it.selected && !it.added);
    for (let i = 0; i < fila.length; i++) {
      if (controller.signal.aborted) break;
      const item = fila[i];
      try {
        const r = await api<ResolvedAddress>("/api/geocode/resolve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: item.text,
            id: item.id,
            origin_lat: origin?.lat,
            origin_lon: origin?.lon,
          }),
          signal: controller.signal,
        });
        update(item.id, { resolved: r, erro: undefined });
        if (AUTOMATICO.includes(r.status) && r.lat !== null && r.lon !== null) {
          addStop({ id: newStopId(), label: r.label, lat: r.lat, lon: r.lon });
          update(item.id, { added: true, selected: false });
        }
      } catch (e) {
        if (controller.signal.aborted) break;
        update(item.id, { erro: e instanceof Error ? e.message : "falhou" });
      }
      setProgresso(Math.round(((i + 1) / fila.length) * 100));
    }

    abortRef.current = null;
    setBusy(false);
    const pendentes = items.some((it) => it.selected && !it.added);
    if (!pendentes && !controller.signal.aborted) setReviewOpen(false);
  };

  const escolherAlternativa = (item: ReviewItem, hit: GeocodeHit) =>
    aceitar(item, hit.label, hit.lat, hit.lon);

  const restantes = items.filter((it) => it.selected && !it.added).length;

  return (
    <div className="modal-backdrop">
      <div className="modal modal-wide">
        <h2>Endereços encontrados</h2>
        <p className="muted">
          Endereços verificados entram na rota automaticamente. Os demais precisam da sua
          confirmação.
        </p>

        {busy && (
          <div className="progress">
            <div className="progress-bar" style={{ width: `${progresso}%` }} />
          </div>
        )}

        <div className="review-list">
          {items.map((item) => {
            const r = item.resolved;
            return (
              <div className="review-item-block" key={item.id}>
                <div className="review-item">
                  <input
                    type="checkbox"
                    checked={item.selected}
                    disabled={item.added || busy}
                    onChange={(e) => update(item.id, { selected: e.target.checked })}
                  />
                  <input
                    type="text"
                    value={item.text}
                    disabled={item.added || busy}
                    onChange={(e) =>
                      update(item.id, { text: e.target.value, resolved: undefined, erro: undefined })
                    }
                  />
                  {item.added && <span className="badge ok">na rota</span>}
                  {!item.added && r && <span className={badgeClass(r.status)}>{ROTULO[r.status]}</span>}
                  {item.erro && <span className="badge err">erro</span>}
                </div>

                {!item.added && r && r.status !== "verificado" && (
                  <div className="review-detail">
                    {r.avisos.map((a) => (
                      <small className="muted" key={a}>
                        ⚠ {AVISO[a] ?? a}
                      </small>
                    ))}
                    {r.checks
                      .filter((c) => !c.ok)
                      .map((c) => (
                        <small className="muted" key={c.nome}>
                          ⚠ {c.nome}: {c.detalhe ?? "não confere"}
                        </small>
                      ))}
                    {r.lat !== null && r.lon !== null && (
                      <button
                        className="btn-link"
                        disabled={busy}
                        onClick={() => aceitar(item, r.label, r.lat!, r.lon!)}
                      >
                        Usar mesmo assim: {r.label}
                      </button>
                    )}
                    {r.alternatives
                      .filter((h) => h.lat !== r.lat || h.lon !== r.lon)
                      .slice(0, 4)
                      .map((h) => (
                        <button
                          className="btn-link"
                          key={`${h.lat},${h.lon}`}
                          disabled={busy}
                          onClick={() => escolherAlternativa(item, h)}
                        >
                          {h.label}
                          {h.region_a ? ` (${h.region_a})` : ""}
                        </button>
                      ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="modal-actions">
          <button className="btn-secondary" onClick={() => setReviewOpen(false)} disabled={busy}>
            Fechar
          </button>
          {busy ? (
            <button className="btn-secondary" onClick={() => abortRef.current?.abort()}>
              Cancelar
            </button>
          ) : (
            <button className="btn-primary" disabled={restantes === 0} onClick={() => void resolver()}>
              Validar e adicionar ({restantes})
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
