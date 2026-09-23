import { useAppStore } from "../../store/useAppStore";

/** A escolha entre tempo e distância muda o resultado do cálculo, então fica ao
 * lado do botão que dispara o cálculo — e não escondida nas configurações. */
export default function OptimizeToggle() {
  const optimizeBy = useAppStore((s) => s.optimizeBy);
  const setOptimizeBy = useAppStore((s) => s.setOptimizeBy);

  return (
    <div className="optimize-row">
      <span className="optimize-label">Otimizar por</span>
      <div className="segmented compact">
        <button
          className={optimizeBy === "duration" ? "active" : ""}
          title="Menor tempo de viagem"
          onClick={() => setOptimizeBy("duration")}
        >
          Tempo
        </button>
        <button
          className={optimizeBy === "distance" ? "active" : ""}
          title="Menor distância percorrida"
          onClick={() => setOptimizeBy("distance")}
        >
          Distância
        </button>
      </div>
    </div>
  );
}
