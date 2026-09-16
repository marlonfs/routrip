import { useAppStore } from "../../store/useAppStore";

export default function CalculateButton() {
  const solve = useAppStore((s) => s.solve);
  const solving = useAppStore((s) => s.solving);
  const origin = useAppStore((s) => s.origin);
  const stops = useAppStore((s) => s.stops);

  return (
    <button
      className="btn-primary full"
      disabled={solving || !origin || stops.length === 0}
      onClick={() => void solve()}
    >
      {solving ? "Calculando rota..." : "Calcular rota"}
    </button>
  );
}
