import { useRef } from "react";
import { useAppStore } from "../../store/useAppStore";

export default function ImageUpload() {
  const runOcr = useAppStore((s) => s.runOcr);
  const ocrLoading = useAppStore((s) => s.ocrLoading);
  const inputRef = useRef<HTMLInputElement>(null);

  const onFiles = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    void runOcr(Array.from(list));
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <section className="card">
      <div className="card-body">
        <button
          className="btn-secondary full"
          disabled={ocrLoading}
          onClick={() => inputRef.current?.click()}
        >
          {ocrLoading ? "Lendo arquivos..." : "📎 Adicionar imagens ou arquivos"}
        </button>
        <small className="muted">
          Fotos de notas/pedidos (OCR) ou planilhas com endereços (.xlsx / CSV)
        </small>
        <input
          ref={inputRef}
          type="file"
          accept="image/*,.csv,.txt,.xlsx,.xlsm"
          multiple
          hidden
          onChange={(e) => onFiles(e.target.files)}
        />
      </div>
    </section>
  );
}
