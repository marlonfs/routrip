import { useEffect, useState } from "react";
import { api, postJson } from "../../api/client";
import { useAppStore } from "../../store/useAppStore";
import type { CnefeStatus } from "../../types";

export default function SettingsPanel() {
  const config = useAppStore((s) => s.config);
  const optimizeBy = useAppStore((s) => s.optimizeBy);
  const setOptimizeBy = useAppStore((s) => s.setOptimizeBy);
  const saveSettings = useAppStore((s) => s.saveSettings);

  const [open, setOpen] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [keyStatus, setKeyStatus] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);
  const [cnefe, setCnefe] = useState<CnefeStatus | null>(null);

  useEffect(() => {
    if (!open || cnefe) return;
    void api<CnefeStatus>("/api/cnefe/status")
      .then(setCnefe)
      .catch(() => undefined);
  }, [open, cnefe]);

  const saveKey = async () => {
    const key = keyInput.trim();
    if (!key) return;
    setValidating(true);
    setKeyStatus(null);
    try {
      const result = await postJson<{ valid: boolean; message: string }>(
        "/api/config/validate-ors-key",
        { api_key: key },
      );
      if (result.valid) {
        await saveSettings({ ors_api_key: key });
        setKeyStatus("Chave válida e salva neste computador.");
        setKeyInput("");
      } else {
        setKeyStatus(result.message);
      }
    } catch (e) {
      setKeyStatus((e as Error).message);
    } finally {
      setValidating(false);
    }
  };

  return (
    <section className="card">
      <button className="card-header" onClick={() => setOpen(!open)}>
        <span>Configurações</span>
        <span className={config?.ors_key_set ? "badge ok" : "badge warn"}>
          {config?.ors_key_set ? "ORS ok" : "sem chave ORS"}
        </span>
        <span>{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="card-body">
          <label className="field">
            <span>Chave da API OpenRouteService</span>
            <div className="row">
              <input
                type="password"
                value={keyInput}
                placeholder={config?.ors_key_set ? config.ors_api_key : "Cole sua chave aqui"}
                onChange={(e) => setKeyInput(e.target.value)}
              />
              <button onClick={saveKey} disabled={validating || !keyInput.trim()}>
                {validating ? "..." : "Salvar"}
              </button>
            </div>
            {keyStatus && <small>{keyStatus}</small>}
            <small>
              {config?.ors_key_set
                ? "Sua chave já está salva neste computador — você só precisa alterá-la se quiser trocar."
                : "Cole a chave uma única vez: ela fica salva neste computador. Obtenha uma chave gratuita em openrouteservice.org"}
            </small>
          </label>

          <div className="field">
            <span>Otimizar rota por</span>
            <div className="segmented">
              <button
                className={optimizeBy === "duration" ? "active" : ""}
                onClick={() => setOptimizeBy("duration")}
              >
                Tempo de viagem
              </button>
              <button
                className={optimizeBy === "distance" ? "active" : ""}
                onClick={() => setOptimizeBy("distance")}
              >
                Distância (km)
              </button>
            </div>
          </div>

          <label className="field">
            <span>Validação de endereços</span>
            <div className="row">
              <input
                type="checkbox"
                checked={config?.validate_addresses ?? true}
                onChange={(e) => void saveSettings({ validate_addresses: e.target.checked })}
              />
              <small>Conferir cada endereço no CEP e na base do IBGE antes de aceitar</small>
            </div>
            <small>
              {cnefe?.disponivel
                ? `Base ${cnefe.fonte}: ${cnefe.n_ceps.toLocaleString("pt-BR")} CEPs em ${cnefe.n_municipios.toLocaleString("pt-BR")} municípios.`
                : "Base do IBGE não encontrada — a validação segue pelo CEP, com menos precisão."}
            </small>
          </label>
        </div>
      )}
    </section>
  );
}
