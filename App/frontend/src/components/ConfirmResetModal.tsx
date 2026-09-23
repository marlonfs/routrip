import { useAppStore } from "../store/useAppStore";

export default function ConfirmResetModal() {
  const stops = useAppStore((s) => s.stops);
  const reset = useAppStore((s) => s.reset);
  const setConfirmReset = useAppStore((s) => s.setConfirmReset);

  return (
    <div className="modal-backdrop">
      <div className="modal modal-narrow">
        <h2>Limpar tudo?</h2>
        <p className="modal-text">
          O ponto de partida, as {stops.length}{" "}
          {stops.length === 1 ? "parada" : "paradas"} e a rota calculada serão
          removidos. Não é possível desfazer.
        </p>
        <div className="modal-actions">
          <button className="btn-neutral" onClick={() => setConfirmReset(false)}>
            Cancelar
          </button>
          <button className="btn-primary small" onClick={reset}>
            Limpar tudo
          </button>
        </div>
      </div>
    </div>
  );
}
