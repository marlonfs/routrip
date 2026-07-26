import os
import sys
from pathlib import Path


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def lkh_path() -> Path:
    env = os.environ.get("LKH_BINARY", "")
    if env and Path(env).is_file():
        return Path(env)
    return resource_root() / "vendor" / "LKH.exe"


def static_dir() -> Path:
    return resource_root() / "static"


def vendored_tesseract() -> Path | None:
    exe = resource_root() / "vendor" / "tesseract" / "tesseract.exe"
    return exe if exe.is_file() else None


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / "Routrip"
    d.mkdir(parents=True, exist_ok=True)
    return d
