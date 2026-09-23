r"""Compara presets de OCR pelo que interessa ao Routrip: endereços extraídos.

Confiança média e taxa de caractere não dizem se a rota vai sair certa. O que decide é
quantos endereços o `address_parser` consegue montar do texto lido, então é isso que o
relatório mostra, lado a lado, para cada imagem.

    python tools\eval_ocr.py <pasta ou imagem> [--presets latin,multi]
    python tools\eval_ocr.py <pasta> --texto        # mostra também as linhas lidas
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from PIL import Image  # noqa: E402

from services import address_parser, ocr, ocr_layout, ocr_preprocess  # noqa: E402

EXTENSOES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def _imagens(alvo: Path) -> list[Path]:
    if alvo.is_file():
        return [alvo]
    return sorted(p for p in alvo.rglob("*") if p.suffix.lower() in EXTENSOES)


def ler_rapidocr(img: Image.Image, preset: str) -> str:
    preparada = ocr_preprocess.preprocess(img)
    return "\n".join(ocr_layout.montar_linhas(ocr.ler_palavras(preparada, preset)))


def main() -> int:
    ap = argparse.ArgumentParser(description="Compara presets de OCR por endereços extraídos.")
    ap.add_argument("alvo", type=Path, help="imagem ou pasta com imagens")
    ap.add_argument("--presets", default="latin",
                    help="presets do RapidOCR separados por vírgula (latin, multi)")
    ap.add_argument("--texto", action="store_true", help="imprimir as linhas lidas")
    args = ap.parse_args()

    if not args.alvo.exists():
        print(f"Caminho não encontrado: {args.alvo}")
        return 1

    imagens = _imagens(args.alvo)
    if not imagens:
        print(f"Nenhuma imagem em {args.alvo} (extensões aceitas: {', '.join(sorted(EXTENSOES))})")
        return 1

    motores: list[tuple[str, callable]] = []
    for preset in [p.strip() for p in args.presets.split(",") if p.strip()]:
        if preset not in ocr.PRESETS:
            print(f"Preset desconhecido: {preset} (disponíveis: {', '.join(ocr.PRESETS)})")
            return 1
        motores.append((f"rapidocr:{preset}",
                        lambda img, _p=preset: ler_rapidocr(img, _p)))

    totais = {nome: [0, 0, 0.0] for nome, _ in motores}  # linhas, endereços, segundos

    for caminho in imagens:
        print(f"\n{'=' * 78}\n{caminho.name}\n{'=' * 78}")
        with Image.open(caminho) as arquivo:
            img = arquivo.copy()
        for nome, ler in motores:
            t0 = time.perf_counter()
            try:
                texto = ler(img)
            except Exception as exc:
                print(f"  {nome:<18} FALHOU: {type(exc).__name__}: {exc}")
                continue
            decorrido = time.perf_counter() - t0
            linhas = [ln for ln in texto.splitlines() if ln.strip()]
            candidatos = address_parser.extract_address_candidates(texto)

            t = totais[nome]
            t[0] += len(linhas)
            t[1] += len(candidatos)
            t[2] += decorrido

            print(f"  {nome:<18} {len(linhas):>3} linhas  "
                  f"{len(candidatos):>2} endereços  {decorrido:>5.2f}s")
            for c in candidatos:
                print(f"       -> {c.cleaned}")
            if args.texto:
                for ln in linhas:
                    print(f"       |  {ln}")

    print(f"\n{'=' * 78}\nTOTAL em {len(imagens)} imagem(ns)\n{'=' * 78}")
    for nome, _ in motores:
        linhas, enderecos, seg = totais[nome]
        print(f"  {nome:<18} {linhas:>4} linhas  {enderecos:>3} endereços  {seg:>6.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
