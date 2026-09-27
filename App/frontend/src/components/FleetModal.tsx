import { useState } from "react";
import { MAX_VEHICLES, useAppStore } from "../store/useAppStore";

const QUICK = [1, 2, 3, 4, 5];

/** Primeira tela do app: quantos veículos a frota tem. Com 1 é o planejador de
 * sempre; com 2 ou mais as paradas são divididas entre os veículos. Na abertura não
 * tem como fechar sem escolher — reaberta pelo cabeçalho, ganha o "Cancelar". */
export default function FleetModal() {
  const vehicles = useAppStore((s) => s.vehicles);
  const setVehicles = useAppStore((s) => s.setVehicles);
  const closeFleet = useAppStore((s) => s.closeFleet);
  const hasResult = useAppStore((s) => s.plan !== null || s.fleet !== null);

  const [choice, setChoice] = useState<number>(vehicles ?? 1);
  const [other, setOther] = useState<string>(
    vehicles !== null && !QUICK.includes(vehicles) ? String(vehicles) : "",
  );

  const firstTime = vehicles === null;
  const valid = Number.isInteger(choice) && choice >= 1 && choice <= MAX_VEHICLES;

  const confirm = () => {
    if (!valid) return;
    if (choice === vehicles) closeFleet();
    else setVehicles(choice);
  };

  return (
    <div className="modal-backdrop">
      <div className="modal modal-narrow fleet-modal">
        <h2>Quantos veículos vão sair?</h2>
        <p className="modal-text">
          Com 1 veículo, o Routrip monta a melhor rota única. Com 2 ou mais, divide as
          paradas entre os veículos — todos saem e voltam ao ponto de partida.
        </p>

        <div className="fleet-options">
          {QUICK.map((n) => (
            <button
              key={n}
              className={choice === n && other === "" ? "active" : ""}
              onClick={() => {
                setChoice(n);
                setOther("");
              }}
              onDoubleClick={() => setVehicles(n)}
            >
              <strong>{n}</strong>
              <small>{n === 1 ? "veículo" : "veículos"}</small>
            </button>
          ))}
        </div>

        <label className="fleet-other">
          <span>Outro número</span>
          <input
            type="number"
            min={1}
            max={MAX_VEHICLES}
            placeholder={`até ${MAX_VEHICLES}`}
            value={other}
            onChange={(e) => {
              setOther(e.target.value);
              const n = Number(e.target.value);
              if (e.target.value !== "") setChoice(n);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") confirm();
            }}
          />
        </label>
        {!valid && (
          <p className="fleet-error">Escolha de 1 a {MAX_VEHICLES} veículos.</p>
        )}
        {!firstTime && hasResult && choice !== vehicles && valid && (
          <p className="fleet-note">
            A partida e as paradas continuam; a rota já calculada é descartada e
            precisa ser calculada de novo.
          </p>
        )}

        <div className="modal-actions">
          {!firstTime && (
            <button className="btn-neutral" onClick={closeFleet}>
              Cancelar
            </button>
          )}
          <button className="btn-primary small" disabled={!valid} onClick={confirm}>
            Continuar
          </button>
        </div>
      </div>
    </div>
  );
}
