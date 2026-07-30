import os
import shutil
from io import BytesIO
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

from core.config import load_config
from core.paths import vendored_tesseract
from services import address_parser, ocr_layout, ocr_preprocess
from services.ocr_layout import Word


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


def _palavras(img: Image.Image, lang: str, psm: str) -> list[Word]:
    dados = pytesseract.image_to_data(img, lang=lang, config=f"--psm {psm}",
                                      output_type=pytesseract.Output.DICT)
    palavras: list[Word] = []
    for i, texto in enumerate(dados["text"]):
        if not texto.strip():
            continue
        # `conf` vem como string em versões antigas do pytesseract e vale -1 nas
        # regiões que o Tesseract classificou como não-texto.
        try:
            conf = float(dados["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf <= 0:
            continue
        palavras.append(Word(texto.strip(), conf, int(dados["left"][i]), int(dados["top"][i]),
                             int(dados["width"][i]), int(dados["height"][i])))
    return palavras


def _pontuar(palavras: list[Word]) -> tuple[float, str]:
    """Julga o PSM pelo que interessa a jusante — quantos endereços saem do texto — e
    não pela confiança bruta. O psm 11 costuma ter confiança menor por ler também
    carimbo e rodapé, e ainda assim extrair mais endereços de um romaneio."""
    texto = "\n".join(ocr_layout.montar_linhas(palavras))
    achados = len(address_parser.extract_address_candidates(texto))
    return achados * ocr_layout.confianca_media(palavras), texto


def extract_text_from_image(img: Image.Image, lang: str = "por") -> str:
    exe = find_tesseract()
    if not exe:
        raise RuntimeError(
            "O componente de OCR (Tesseract) não foi encontrado na instalação do aplicativo. "
            "Reinstale o Routrip."
        )
    _configure(exe)
    cfg = load_config()
    if cfg.ocr_preprocess:
        img = ocr_preprocess.preprocess(img)
    else:
        img = ImageOps.autocontrast(ImageOps.grayscale(ImageOps.exif_transpose(img)))

    modos = ("6", "11") if cfg.ocr_psm_mode == "auto" else (cfg.ocr_psm_mode,)
    melhor, melhor_score = "", -1.0
    for psm in modos:
        try:
            palavras = _palavras(img, lang, psm)
        except pytesseract.TesseractError:
            if lang == "eng":
                raise
            # Idioma ausente no pacote: a troca vale para os modos seguintes também.
            lang = "eng"
            palavras = _palavras(img, lang, psm)
        score, texto = _pontuar(palavras)
        if score > melhor_score:
            melhor, melhor_score = texto, score
    return melhor


def extract_text(image_bytes: bytes, lang: str = "por") -> str:
    return extract_text_from_image(Image.open(BytesIO(image_bytes)), lang=lang)
