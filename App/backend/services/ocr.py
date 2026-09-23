r"""Motor de OCR: detecção + reconhecimento neural (PP-OCR) via onnxruntime.

Substituiu o Tesseract, que não dava conta de foto de romaneio e nota fiscal. O contrato
com o resto do aplicativo não mudou: entra imagem, sai uma string com uma linha por
`\n`, pronta para `address_parser.extract_address_candidates`.
"""

import os
import threading
from io import BytesIO
from pathlib import Path

from PIL import Image

from core.config import load_config
from core.paths import resource_root, vendored_ocr_dir
from services import ocr_layout, ocr_preprocess
from services.ocr_layout import Word

# Detecção e reconhecimento são estágios independentes, então a versão de cada um é
# escolhida à parte. O reconhecedor `latin` cobre todo o português (inclusive maiúsculas
# acentuadas) em 7,5 MB; o multilíngue do PP-OCRv6 lê igual e ocupa 20 MB.
PRESETS: dict[str, dict[str, str]] = {
    "latin": {
        "det_version": "PP-OCRv6", "det_type": "small",
        "rec_version": "PP-OCRv5", "rec_type": "mobile", "rec_lang": "latin",
    },
    "multi": {
        "det_version": "PP-OCRv6", "det_type": "small",
        "rec_version": "PP-OCRv6", "rec_type": "small", "rec_lang": "pt",
    },
}
PRESET_PADRAO = "latin"

# O padrão do RapidOCR (limit_type "min", 736) encolhe uma foto de A4 para ~736 px de
# menor lado e apaga o texto miúdo do romaneio. Aqui o limite é o lado MAIOR, e mais alto.
LIMITE_LADO = 1600
# Abaixo do padrão (0.5): linha fraca de impressora matricial ou térmica desbotada ainda
# interessa. Ruído extra é barato — o parser já descarta linha com menos de 6 caracteres.
BOX_THRESH = 0.4
TEXT_SCORE = 0.4
# Abaixo disto a leitura é fraca o bastante para valer testar outra orientação: ~4 linhas
# com score médio 0,8 já passa, e documento deitado fica muito longe disso.
MIN_QUALIDADE = 320.0

_lock = threading.Lock()
_motores: dict[str, object] = {}


def preset_ativo() -> str:
    nome = os.environ.get("ROUTRIP_OCR_PRESET", "").strip().lower()
    return nome if nome in PRESETS else PRESET_PADRAO


def _construir(preset: str, diretorio: Path):
    from rapidocr import ModelType, OCRVersion, RapidOCR

    p = PRESETS[preset]
    return RapidOCR(params={
        "Global.model_root_dir": str(diretorio),
        "Global.text_score": TEXT_SCORE,
        "Global.max_side_len": LIMITE_LADO,
        "Global.log_level": "error",
        "Det.ocr_version": OCRVersion(p["det_version"]),
        "Det.model_type": ModelType(p["det_type"]),
        "Det.lang_type": "pt",
        "Det.limit_type": "max",
        "Det.limit_side_len": LIMITE_LADO,
        "Det.box_thresh": BOX_THRESH,
        "Rec.ocr_version": OCRVersion(p["rec_version"]),
        "Rec.model_type": ModelType(p["rec_type"]),
        "Rec.lang_type": p["rec_lang"],
    })


def baixar_modelos(preset: str | None = None) -> Path:
    """Passo de setup (scripts/get_ocr_models.ps1), não do aplicativo: construir o motor
    apontando o destino faz o rapidocr baixar os ONNX e conferir o SHA256 do catálogo
    dele. `_motor` não serve aqui porque recusa rodar justamente quando falta modelo."""
    destino = resource_root() / "vendor" / "ocr"
    destino.mkdir(parents=True, exist_ok=True)
    _construir(preset or preset_ativo(), destino)
    return destino


def _motor(preset: str):
    """Instância única por preset: carregar os três ONNX custa ~1 s e o endpoint do
    FastAPI é síncrono, ou seja, roda em threadpool e entra aqui concorrentemente. A
    sessão do onnxruntime é thread-safe para inferência, só a construção precisa do lock."""
    motor = _motores.get(preset)
    if motor is not None:
        return motor

    with _lock:
        if preset in _motores:
            return _motores[preset]

        diretorio = vendored_ocr_dir()
        if diretorio is None or not any(diretorio.glob("*.onnx")):
            raise RuntimeError(
                "Os modelos de OCR não foram encontrados na instalação do aplicativo. "
                "Reinstale o Routrip."
            )

        motor = _construir(preset, diretorio)
        _motores[preset] = motor
        return motor


def ler_palavras(img: Image.Image, preset: str | None = None) -> list[Word]:
    """Uma `Word` por linha detectada. O PP-OCR já entrega a linha inteira reconhecida,
    então a montagem em `ocr_layout` serve para fundir colunas lado a lado e manter a
    ordem de leitura — o mesmo papel que tinha com as palavras soltas do Tesseract."""
    resultado = _motor(preset or preset_ativo())(img)
    caixas, textos, scores = resultado.boxes, resultado.txts, resultado.scores
    if caixas is None or not textos:
        return []

    palavras: list[Word] = []
    for caixa, texto, score in zip(caixas, textos, scores):
        if not texto.strip():
            continue
        xs = [float(p[0]) for p in caixa]
        ys = [float(p[1]) for p in caixa]
        esquerda, topo = min(xs), min(ys)
        palavras.append(Word(
            texto.strip(),
            # O Tesseract dava confiança em 0-100 e `ocr_layout.confianca_media` ficou
            # nessa escala; o PP-OCR devolve 0-1.
            float(score) * 100.0,
            int(esquerda), int(topo),
            int(max(xs) - esquerda), int(max(ys) - topo),
        ))
    return palavras


def _qualidade(palavras: list[Word]) -> float:
    """Quanto texto legível saiu. Serve para comparar orientações, não para julgar a
    imagem: uma foto deitada devolve poucas caixas e com score baixo."""
    if not palavras:
        return 0.0
    return len(palavras) * (sum(p.conf for p in palavras) / len(palavras))


def _ler_orientando(img: Image.Image, preset: str) -> list[Word]:
    """O Tesseract trazia OSD (`image_to_osd`) para descobrir foto deitada; sem ele, a
    saída é comparar as leituras. Só vale pagar as passadas extras quando a primeira vem
    fraca — o giro de 180° por linha o classificador de orientação já resolve sozinho."""
    palavras = ler_palavras(img, preset)
    if _qualidade(palavras) >= MIN_QUALIDADE:
        return palavras

    melhor, melhor_q = palavras, _qualidade(palavras)
    for graus in (90, 270):
        tentativa = ler_palavras(img.rotate(graus, expand=True), preset)
        q = _qualidade(tentativa)
        if q > melhor_q:
            melhor, melhor_q = tentativa, q
    return melhor


def extract_text_from_image(img: Image.Image) -> str:
    cfg = load_config()
    preset = preset_ativo()
    img = ocr_preprocess.preprocess(img) if cfg.ocr_preprocess else ocr_preprocess.endireitar(img)
    linhas = ocr_layout.montar_linhas(_ler_orientando(img, preset))
    return "\n".join(linhas)


def extract_text(image_bytes: bytes) -> str:
    return extract_text_from_image(Image.open(BytesIO(image_bytes)))
