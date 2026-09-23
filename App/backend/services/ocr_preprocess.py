"""Correção geométrica antes do OCR.

Não binariza: o PP-OCR é uma rede treinada em imagem colorida e usa gradiente e
contraste como sinal, ao contrário do Tesseract, que trabalhava sobre um limiar. Aqui
o trabalho é só deixar o texto na horizontal e grande o bastante.
"""

from PIL import Image, ImageOps

LADO_MENOR_ALVO = 1600
LADO_MAIOR_TETO = 4000
ANGULO_MAX = 7.0
PASSO_ANGULO = 0.5


def _cv2():
    import cv2
    import numpy as np
    return cv2, np


def endireitar(img: Image.Image) -> Image.Image:
    """Só a rotação que a câmera registrou no EXIF, sem tocar no conteúdo."""
    return ImageOps.exif_transpose(img).convert("RGB")


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


def preprocess(img: Image.Image) -> Image.Image:
    img = _upscale(endireitar(img))

    try:
        cv2, np = _cv2()
    except ImportError:
        return img

    arr = np.array(img)
    # O ângulo é medido no cinza, mas a rotação é aplicada na imagem colorida: o
    # reconhecedor recebe a cor original.
    angulo = _angulo_por_projecao(cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY), cv2, np)
    if abs(angulo) < PASSO_ANGULO:
        return img

    altura, largura = arr.shape[:2]
    m = cv2.getRotationMatrix2D((largura / 2, altura / 2), angulo, 1.0)
    arr = cv2.warpAffine(arr, m, (largura, altura), flags=cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(arr)
