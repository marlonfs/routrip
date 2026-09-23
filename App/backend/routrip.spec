# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files

datas = [
    ("static", "static"),
    # Inclui vendor/ocr (modelos .onnx) e vendor/LKH.exe.
    ("vendor", "vendor"),
    # config.yaml e default_models.yaml, que o rapidocr lê do próprio pacote. Só os
    # YAML: o pacote também guarda em models/ um cache dos .onnx que ele já baixou
    # alguma vez, e levá-lo duplicaria dezenas de MB do que vendor/ocr já traz.
    *[(src, dst) for src, dst in collect_data_files("rapidocr") if src.endswith(".yaml")],
]

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "webview.platforms.edgechromium",
    # O import do cv2 é lazy, dentro de ocr_preprocess._cv2(), para que uma falha de
    # empacotamento degrade o OCR em vez de derrubar o aplicativo.
    "cv2",
    "numpy",
    "onnxruntime",
    "rapidocr",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Routrip",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Routrip",
)
