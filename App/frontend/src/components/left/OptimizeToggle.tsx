import { useAppStore } from "../../store/useAppStore";

/** A escolha entre tempo e distância muda o resultado do cálculo, então fica ao
 * lado do botão que dispara o cálculo — e não escondida nas configurações. */
export default function OptimizeToggle() {
  const optimizeBy = useAppStore((s) => s.optimizeBy);
  const setOptimizeBy = useAppStore((s) => s.setOptimizeBy);
  // Com frota, cada critério vira um objetivo diferente: tempo encurta a rota mais
  // longa (o dia acaba antes), distância encurta a soma de todas.
  const fleet = (useAppStore((s) => s.vehicles) ?? 1) > 1;

  return (
    <div className="optimize-row">
      <span className="optimize-label">Otimizar por</span>
      <div className="segmented compact">
        <button
          className={optimizeBy === "duration" ? "active" : ""}
          title={fleet ? "O último veículo volta o mais cedo possível" : "Menor tempo de viagem"}
          onClick={() => setOptimizeBy("duration")}
        >
          Tempo
        </button>
        <button
          className={optimizeBy === "distance" ? "active" : ""}
          title={fleet ? "Menor soma de quilômetros da frota" : "Menor distância percorrida"}
          onClick={() => setOptimizeBy("distance")}
        >
          Distância
        </button>
      </div>
    </div>
  );
}
