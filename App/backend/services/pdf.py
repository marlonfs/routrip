import pypdfium2 as pdfium

from services import ocr

# ~165 dpi: resolução suficiente para o Tesseract ler notas fiscais rasterizadas
RENDER_SCALE = 2.3
MIN_NATIVE_CHARS = 40


def _has_text_layer(text: str) -> bool:
    return sum(ch.isalnum() for ch in text) >= MIN_NATIVE_CHARS


def extract_text(content: bytes, lang: str = "por") -> str:
    try:
        doc = pdfium.PdfDocument(content)
    except pdfium.PdfiumError as exc:
        raise RuntimeError(
            f"Não foi possível ler o PDF ({exc}). Se ele estiver protegido por senha, "
            "remova a proteção e tente novamente."
        )

    try:
        pages: list[str] = []
        for page in doc:
            native = page.get_textpage().get_text_bounded()
            if _has_text_layer(native):
                pages.append(native)
            else:
                pages.append(
                    ocr.extract_text_from_image(page.render(scale=RENDER_SCALE).to_pil(), lang=lang)
                )
        return "\n".join(pages)
    finally:
        doc.close()
