"""Pré-processamento de imagem antes do OCR: upscale, deskew e binarização.

O OpenCV é importado dentro das funções e toda falha degrada para o caminho só-PIL.
Empacotamento quebrado deve piorar o OCR, não derrubar o aplicativo — mesmo critério
já usado em find_tesseract().
"""

from PIL import Image, ImageOps

LADO_MENOR_ALVO = 1600
LADO_MAIOR_TETO = 4000
ANGULO_MAX = 7.0
PASSO_ANGULO = 0.5
# Abaixo disto o fundo é uniforme e o Otsu interno do Tesseract 5 lê melhor o cinza
# do que qualquer binarização nossa. Acima, há sombra ou iluminação irregular.
DESVIO_FUNDO_LIMIAR = 18.0


def _cv2():
    import cv2
    import numpy as np

    return cv2, np


def _upscale(img: Image.Image) -> Image.Image:
    menor = min(img.size)
    if menor >= LADO_MENOR_ALVO:
        return img
    fator = min(LADO_MENOR_ALVO / menor, LADO_MAIOR_TETO / max(img.size))
    if fator <= 1.0:
        return img
    novo = (round(img.width * fator), round(img.height * fator))
    return img.resize(novo, Image.BICUBIC)


def _angulo_por_projecao(arr, cv2, np) -> float:
    """Projection profile: a variância da soma por linha é máxima quando as linhas de
    texto estão horizontais. minAreaRect erra feio quando a foto tem logo, tabela ou
    borda escura — que é exatamente o caso de nota fiscal e romaneio."""
    binario = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    escala = 600 / max(binario.shape)
    if escala < 1.0:
        binario = cv2.resize(binario, None, fx=escala, fy=escala,
                             interpolation=cv2.INTER_AREA)

    altura, largura = binario.shape
    centro = (largura / 2, altura / 2)
    melhor_angulo, melhor_score = 0.0, -1.0
    passos = int(ANGULO_MAX / PASSO_ANGULO)
    for i in range(-passos, passos + 1):
        angulo = i * PASSO_ANGULO
        m = cv2.getRotationMatrix2D(centro, angulo, 1.0)
        girado = cv2.warpAffine(binario, m, (largura, altura), flags=cv2.INTER_NEAREST)
        score = float(np.var(girado.sum(axis=1, dtype=np.float64)))
        if score > melhor_score:
            melhor_angulo, melhor_score = angulo, score
    return melhor_angulo


def _rotacao_grosseira(img: Image.Image) -> Image.Image:
    """90/180/270 pelo OSD do Tesseract; o projection profile só resolve inclinações
    pequenas e daria resultado sem sentido numa foto deitada."""
    import pytesseract

    try:
        osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
        graus = int(osd.get("rotate", 0)) % 360
    except Exception:
        return img
    if graus in (90, 180, 270):
        return img.rotate(-graus, expand=True)
    return img


def preprocess(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    img = _rotacao_grosseira(img)
    img = ImageOps.grayscale(img)
    img = _upscale(img)

    try:
        cv2, np = _cv2()
    except ImportError:
        return ImageOps.autocontrast(img)

    arr = np.array(img)
    angulo = _angulo_por_projecao(arr, cv2, np)
    if abs(angulo) >= PASSO_ANGULO:
        altura, largura = arr.shape
        m = cv2.getRotationMatrix2D((largura / 2, altura / 2), angulo, 1.0)
        arr = cv2.warpAffine(arr, m, (largura, altura), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_REPLICATE)

    fundo = cv2.GaussianBlur(arr, (0, 0), sigmaX=max(arr.shape) / 30)
    if float(np.std(fundo)) > DESVIO_FUNDO_LIMIAR:
        arr = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, 31, 15)
    else:
        arr = cv2.normalize(arr, None, 0, 255, cv2.NORM_MINMAX)
    return Image.fromarray(arr)
