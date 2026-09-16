import { useEffect } from "react";
import AddressList from "./components/left/AddressList";
import AddressSearch from "./components/left/AddressSearch";
import CalculateButton from "./components/left/CalculateButton";
import ImageUpload from "./components/left/ImageUpload";
import OcrReviewModal from "./components/left/OcrReviewModal";
import SettingsPanel from "./components/left/SettingsPanel";
import SpreadsheetModal from "./components/left/SpreadsheetModal";
import MapView from "./components/center/MapView";
import ItineraryPanel from "./components/right/ItineraryPanel";
import { useAppStore } from "./store/useAppStore";

export default function App() {
  const loadConfig = useAppStore((s) => s.loadConfig);
  const reviewOpen = useAppStore((s) => s.reviewOpen);
  const spreadsheet = useAppStore((s) => s.spreadsheet);
  const error = useAppStore((s) => s.error);
  const setError = useAppStore((s) => s.setError);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  return (
    <div className="app">
      <header className="topbar">
        <span className="topbar-brand">Routrip</span>
        <span className="topbar-sub">Planejador de rotas de entrega</span>
      </header>
      <aside className="panel panel-left">
        <div className="panel-title">Planejamento</div>
        <SettingsPanel />
        <ImageUpload />
        <AddressSearch />
        <AddressList />
        <CalculateButton />
      </aside>
      <main className="map-area">
        <MapView />
        {error && (
          <div className="toast" onClick={() => setError(null)}>
            {error}
            <span className="toast-close">×</span>
          </div>
        )}
      </main>
      <aside className="panel panel-right">
        <div className="panel-title">Itinerário</div>
        <ItineraryPanel />
      </aside>
      {spreadsheet && <SpreadsheetModal preview={spreadsheet} />}
      {reviewOpen && <OcrReviewModal />}
    </div>
  );
}
