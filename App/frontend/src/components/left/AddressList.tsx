import { useAppStore } from "../../store/useAppStore";

export default function AddressList() {
  const origin = useAppStore((s) => s.origin);
  const stops = useAppStore((s) => s.stops);
  const setOrigin = useAppStore((s) => s.setOrigin);
  const removeStop = useAppStore((s) => s.removeStop);

  return (
    <section className="card grow">
      <div className="card-header static">
        <span>Endereços ({stops.length})</span>
      </div>
      <div className="card-body list">
        <div className="addr-item origin">
          <span className="dot origin-dot" />
          {origin ? (
            <>
              <span className="addr-label" title={origin.label}>{origin.label}</span>
              <button className="btn-icon" title="Remover partida" onClick={() => setOrigin(null)}>
                ×
              </button>
            </>
          ) : (
            <span className="addr-placeholder">
              Defina o ponto de partida (busca ou botão direito no mapa)
            </span>
          )}
        </div>
        {stops.map((s, i) => (
          <div className="addr-item" key={s.id}>
            <span className="dot stop-dot">{i + 1}</span>
            <span className="addr-label" title={s.label}>{s.label}</span>
            <button className="btn-icon" title="Remover" onClick={() => removeStop(s.id)}>
              ×
            </button>
          </div>
        ))}
        {stops.length === 0 && (
          <p className="addr-placeholder">
            Adicione paradas pela busca ou envie imagens para OCR.
          </p>
        )}
      </div>
    </section>
  );
}
