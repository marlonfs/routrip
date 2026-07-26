import csv
import io

from openpyxl import load_workbook


def _fmt_cell(cell) -> str:
    if isinstance(cell, float) and cell.is_integer():
        return str(int(cell))
    return str(cell).strip()


def _lines_from_rows(rows) -> list[str]:
    lines = []
    for row in rows:
        cells = [_fmt_cell(c) for c in row if c is not None and _fmt_cell(c)]
        if cells:
            lines.append(", ".join(cells))
    return lines


def lines_from_csv(content: bytes) -> list[str]:
    text = None
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = content.decode("latin-1", errors="replace")

    sample = text[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        # Planilhas brasileiras costumam usar ';'
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    return _lines_from_rows(csv.reader(io.StringIO(text), delimiter=delimiter))


def lines_from_xlsx(content: bytes) -> list[str]:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        lines: list[str] = []
        for ws in wb.worksheets:
            lines.extend(_lines_from_rows(ws.iter_rows(values_only=True)))
        return lines
    finally:
        wb.close()
