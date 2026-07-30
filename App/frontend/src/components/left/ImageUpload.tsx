import { useRef } from "react";
import { useAppStore } from "../../store/useAppStore";

export default function ImageUpload() {
  const importFiles = useAppStore((s) => s.importFiles);
  const importLoading = useAppStore((s) => s.importLoading);
  const origin = useAppStore((s) => s.origin);
  const inputRef = useRef<HTMLInputElement>(null);

  const onFiles = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    void importFiles(Array.from(list));
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <section className="card">
      <div className="card-body">
        <button
          className="btn-secondary full"
          disabled={importLoading || !origin}
          title={origin ? undefined : "Defina o ponto de partida antes de importar endereços"}
          onClick={() => inputRef.current?.click()}
        >
          {importLoading ? "Lendo arquivos..." : "📎 Adicionar imagens ou arquivos"}
        </button>
        <small className="muted">
          {origin
            ? "Fotos e PDFs de notas/pedidos (OCR) ou planilhas com endereços (.xlsx / CSV)"
            : "Defina o ponto de partida primeiro: ele orienta a busca dos endereços importados."}
        </small>
        <input
          ref={inputRef}
          type="file"
          accept="image/*,.pdf,.csv,.txt,.xlsx,.xlsm"
          multiple
          hidden
          onChange={(e) => onFiles(e.target.files)}
        />
      </div>
    </section>
  );
}
