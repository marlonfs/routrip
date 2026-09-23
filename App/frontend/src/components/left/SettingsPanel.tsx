import { useEffect, useState } from "react";
import { api, postJson } from "../../api/client";
import { useAppStore } from "../../store/useAppStore";
import type { CnefeStatus } from "../../types";

export default function SettingsPanel() {
  const config = useAppStore((s) => s.config);
  const saveSettings = useAppStore((s) => s.saveSettings);
  const closeSettings = useAppStore((s) => s.closeSettings);

  const [keyInput, setKeyInput] = useState("");
  const [keyStatus, setKeyStatus] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);
  const [cnefe, setCnefe] = useState<CnefeStatus | null>(null);

  useEffect(() => {
    void api<CnefeStatus>("/api/cnefe/status")
      .then(setCnefe)
      .catch(() => undefined);
  }, []);

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
    <div className="view">
      <div className="settings-head">
        <button className="btn-back" title="Voltar" onClick={closeSettings}>
          ←
        </button>
        <span className="settings-title">Configurações</span>
        <span className={config?.ors_key_set ? "badge ok" : "badge warn"}>
          {config?.ors_key_set ? "ORS ok" : "sem chave ORS"}
        </span>
      </div>

      <div className="settings-body">
        <label className="field">
          <span>Chave da API OpenRouteService</span>
          <div className="row">
            <input
              type="password"
              value={keyInput}
              placeholder={config?.ors_key_set ? config.ors_api_key : "Cole sua chave aqui"}
              onChange={(e) => setKeyInput(e.target.value)}
            />
            <button
              className="btn-secondary"
              onClick={saveKey}
              disabled={validating || !keyInput.trim()}
            >
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
          <span>Validação de endereços</span>
          <p className="note-card">
            Todo endereço é conferido no CEP e na base do IBGE antes de entrar na rota.
          </p>
          <small>
            {cnefe?.disponivel
              ? `Base ${cnefe.fonte}: ${cnefe.n_ceps.toLocaleString("pt-BR")} CEPs em ${cnefe.n_municipios.toLocaleString("pt-BR")} municípios.`
              : "Base do IBGE não encontrada — a validação segue pelo CEP, com menos precisão."}
          </small>
          {cnefe?.disponivel && (
            <small className={cnefe.numeracao ? "muted" : "warn-text"}>
              {cnefe.numeracao
                ? `${cnefe.n_numeros.toLocaleString("pt-BR")} números de casa com coordenada própria — o pino cai na porta.`
                : "Esta base não tem a numeração das casas: o número é estimado ao "
                  + "longo da rua e erra cerca de 100 m. Atualize a base para corrigir."}
            </small>
          )}
        </div>
      </div>
    </div>
  );
}
