import { useMemo, useState } from "react";
import { useAppStore } from "../../store/useAppStore";
import type { SpreadsheetPreview, SpreadsheetSheet } from "../../types";

const HEADER_HINT = /endere[çc]o|logradouro|rua|avenida|destino|local|address/i;
const ADDRESS_HINT =
  /\b(rua|r\.|av\.?|avenida|travessa|alameda|rodovia|estrada|pra[çc]a)\b|\b\d{5}-?\d{3}\b/i;

function columnLabel(index: number): string {
  let label = "";
  for (let n = index; n >= 0; n = Math.floor(n / 26) - 1) {
    label = String.fromCharCode(65 + (n % 26)) + label;
  }
  return label;
}

function looksLikeHeader(rows: string[][]): boolean {
  const first = rows[0] ?? [];
  return first.some((cell) => cell !== "") && first.every((cell) => !/\d/.test(cell));
}

/** Sugere a coluna de endereços pelo título ou, sem título, pela coluna com mais
 * células parecidas com logradouro/CEP. */
function suggestColumn(sheet: SpreadsheetSheet, hasHeader: boolean): number {
  if (hasHeader) {
    const byTitle = sheet.rows[0].findIndex((cell) => HEADER_HINT.test(cell));
    if (byTitle >= 0) return byTitle;
  }
  const body = hasHeader ? sheet.rows.slice(1) : sheet.rows;
  const width = sheet.rows[0]?.length ?? 0;
  let best = -1;
  let bestHits = 0;
  for (let col = 0; col < width; col++) {
    const hits = body.filter((row) => ADDRESS_HINT.test(row[col] ?? "")).length;
    if (hits > bestHits) {
      bestHits = hits;
      best = col;
    }
  }
  return best;
}

function suggestSelection(sheet: SpreadsheetSheet, hasHeader: boolean): Set<string> {
  const selected = new Set<string>();
  const col = suggestColumn(sheet, hasHeader);
  if (col < 0) return selected;
  for (let row = hasHeader ? 1 : 0; row < sheet.rows.length; row++) {
    selected.add(`${row}:${col}`);
  }
  return selected;
}

export default function SpreadsheetModal({ preview }: { preview: SpreadsheetPreview }) {
  const addSpreadsheetLines = useAppStore((s) => s.addSpreadsheetLines);
  const skipSpreadsheet = useAppStore((s) => s.skipSpreadsheet);

  const sheets = useMemo(
    () => preview.sheets.filter((s) => s.rows.length > 0),
    [preview],
  );
  const [sheetIndex, setSheetIndex] = useState(0);
  const [hasHeader, setHasHeader] = useState(() => looksLikeHeader(sheets[0].rows));
  const [selected, setSelected] = useState(() =>
    suggestSelection(sheets[0], looksLikeHeader(sheets[0].rows)),
  );

  const sheet = sheets[sheetIndex];
  const width = sheet.rows[0]?.length ?? 0;
  const firstDataRow = hasHeader ? 1 : 0;

  const selectSheet = (index: number) => {
    const header = looksLikeHeader(sheets[index].rows);
    setSheetIndex(index);
    setHasHeader(header);
    setSelected(suggestSelection(sheets[index], header));
  };

  const changeHasHeader = (checked: boolean) => {
    setHasHeader(checked);
    setSelected(suggestSelection(sheet, checked));
  };

  const columnFullySelected = (col: number) =>
    sheet.rows.length > firstDataRow &&
    sheet.rows.every((_, row) => row < firstDataRow || selected.has(`${row}:${col}`));

  const toggleColumn = (col: number) => {
    const remove = columnFullySelected(col);
    setSelected((prev) => {
      const next = new Set(prev);
      for (let row = firstDataRow; row < sheet.rows.length; row++) {
        if (remove) next.delete(`${row}:${col}`);
        else next.add(`${row}:${col}`);
      }
      return next;
    });
  };

  const toggleCell = (row: number, col: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      const key = `${row}:${col}`;
      if (!next.delete(key)) next.add(key);
      return next;
    });

  const lines = useMemo(() => {
    const result: string[] = [];
    sheet.rows.forEach((row, r) => {
      if (r < firstDataRow) return;
      const cells = row
        .filter((_, c) => selected.has(`${r}:${c}`))
        .map((cell) => cell.trim())
        .filter(Boolean);
      if (cells.length > 0) result.push(cells.join(", "));
    });
    return result;
  }, [sheet, firstDataRow, selected]);

  return (
    <div className="modal-backdrop">
      <div className="modal modal-wide">
        <h2>Onde estão os endereços?</h2>
        <p className="muted">
          {preview.filename} — clique no título para marcar a coluna inteira ou em células
          específicas. Células marcadas na mesma linha formam um endereço.
        </p>

        {sheets.length > 1 && (
          <div className="sheet-tabs">
            {sheets.map((s, i) => (
              <button
                key={s.name}
                className={i === sheetIndex ? "sheet-tab active" : "sheet-tab"}
                onClick={() => selectSheet(i)}
              >
                {s.name}
              </button>
            ))}
          </div>
        )}

        <label className="check-line">
          <input
            type="checkbox"
            checked={hasHeader}
            onChange={(e) => changeHasHeader(e.target.checked)}
          />
          A primeira linha contém os títulos das colunas
        </label>

        <div className="sheet-scroll">
          <table className="sheet-grid">
            <thead>
              <tr>
                <th className="sheet-rownum" />
                {Array.from({ length: width }, (_, col) => (
                  <th
                    key={col}
                    className={columnFullySelected(col) ? "selected" : undefined}
                    onClick={() => toggleColumn(col)}
                    title="Marcar ou desmarcar a coluna"
                  >
                    {(hasHeader && sheet.rows[0][col]) || columnLabel(col)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sheet.rows.slice(firstDataRow).map((row, i) => {
                const r = i + firstDataRow;
                return (
                  <tr key={r}>
                    <th className="sheet-rownum">{r + 1}</th>
                    {Array.from({ length: width }, (_, col) => (
                      <td
                        key={col}
                        className={selected.has(`${r}:${col}`) ? "selected" : undefined}
                        onClick={() => toggleCell(r, col)}
                      >
                        {row[col]}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {sheet.truncated && (
          <small className="muted">
            Exibindo as primeiras {sheet.rows.length} linhas de {sheet.total_rows}.
          </small>
        )}

        <div className="modal-actions">
          <span className="muted spacer-left">
            {lines.length} {lines.length === 1 ? "endereço" : "endereços"} selecionados
          </span>
          <button className="btn-secondary" onClick={skipSpreadsheet}>
            Cancelar
          </button>
          <button
            className="btn-primary"
            disabled={lines.length === 0}
            onClick={() => void addSpreadsheetLines(lines)}
          >
            Usar selecionados
          </button>
        </div>
      </div>
    </div>
  );
}
