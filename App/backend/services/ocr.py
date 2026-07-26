import os
import shutil
from io import BytesIO
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

from core.paths import vendored_tesseract


def find_tesseract() -> str | None:
    candidates: list[Path] = []
    vendored = vendored_tesseract()
    if vendored:
        candidates.append(vendored)
    which = shutil.which("tesseract")
    if which:
        candidates.append(Path(which))
    candidates.append(Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"))
    candidates.append(Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"))
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def _configure(exe: str) -> None:
    pytesseract.pytesseract.tesseract_cmd = exe
    tessdata = Path(exe).parent / "tessdata"
    if tessdata.is_dir():
        os.environ["TESSDATA_PREFIX"] = str(tessdata)


def extract_text(image_bytes: bytes, lang: str = "por") -> str:
    exe = find_tesseract()
    if not exe:
        raise RuntimeError(
            "O componente de OCR (Tesseract) não foi encontrado na instalação do aplicativo. "
            "Reinstale o Routrip."
        )
    _configure(exe)
    img = Image.open(BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img)
    try:
        return pytesseract.image_to_string(img, lang=lang, config="--psm 6")
    except pytesseract.TesseractError:
        if lang != "eng":
            return pytesseract.image_to_string(img, lang="eng", config="--psm 6")
        raise
