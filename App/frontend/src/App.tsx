import { useEffect } from "react";
import AddressList from "./components/left/AddressList";
import AddressSearch from "./components/left/AddressSearch";
import CalculateButton from "./components/left/CalculateButton";
import ImageUpload from "./components/left/ImageUpload";
import OcrReviewModal from "./components/left/OcrReviewModal";
import OptimizeToggle from "./components/left/OptimizeToggle";
import SettingsPanel from "./components/left/SettingsPanel";
import SpreadsheetModal from "./components/left/SpreadsheetModal";
import ConfirmResetModal from "./components/ConfirmResetModal";
import MapView from "./components/center/MapView";
import ItineraryPanel from "./components/right/ItineraryPanel";
import { useAppStore } from "./store/useAppStore";

function PlanView() {
  return (
    <div className="view">
      <div className="plan-top">
        <AddressSearch />
        <ImageUpload />
      </div>
      <AddressList />
      <div className="panel-foot column">
        <OptimizeToggle />
        <CalculateButton />
      </div>
    </div>
  );
}

export default function App() {
  const loadConfig = useAppStore((s) => s.loadConfig);
  const reviewOpen = useAppStore((s) => s.reviewOpen);
  const spreadsheet = useAppStore((s) => s.spreadsheet);
  const confirmReset = useAppStore((s) => s.confirmReset);
  const error = useAppStore((s) => s.error);
  const setError = useAppStore((s) => s.setError);
  const config = useAppStore((s) => s.config);
  const stops = useAppStore((s) => s.stops);
  const tab = useAppStore((s) => s.tab);
  const setTab = useAppStore((s) => s.setTab);
  const openSettings = useAppStore((s) => s.openSettings);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  return (
    <div className="app">
      <main className="map-area">
        <MapView />
      </main>

      <aside className="panel">
        {tab !== "settings" && (
          <>
            <div className="panel-head">
              <div className="brand">
                <span className="brand-name">Routrip</span>
                <span className="brand-sub">Planejador de rotas de entrega</span>
              </div>
              <button className="settings-open" onClick={openSettings}>
                Configurações
                <span className={config?.ors_key_set ? "status-dot" : "status-dot off"} />
              </button>
            </div>
            <div className="tabs">
              <button
                className={tab === "plan" ? "active" : ""}
                onClick={() => setTab("plan")}
              >
                Planejamento · {stops.length}
              </button>
              <button
                className={tab === "route" ? "active" : ""}
                onClick={() => setTab("route")}
              >
                Itinerário
              </button>
            </div>
          </>
        )}

        {tab === "plan" && <PlanView />}
        {tab === "route" && <ItineraryPanel />}
        {tab === "settings" && <SettingsPanel />}
      </aside>

      {error && (
        <div className="toast" onClick={() => setError(null)}>
          {error}
          <span className="toast-close">×</span>
        </div>
      )}
      {confirmReset && <ConfirmResetModal />}
      {spreadsheet && <SpreadsheetModal preview={spreadsheet} />}
      {reviewOpen && <OcrReviewModal />}
    </div>
  );
}
