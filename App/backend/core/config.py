import json
import os
import tempfile
from typing import Literal

from pydantic import BaseModel

from core.paths import app_data_dir


class AppConfig(BaseModel):
    ors_api_key: str = ""
    optimize_by: Literal["duration", "distance"] = "duration"
    departure_time: str = "08:00"
    stop_minutes: int = 10
    validate_addresses: bool = True
    ocr_preprocess: bool = True
    ocr_psm_mode: Literal["auto", "6", "11"] = "auto"


def _config_file():
    return app_data_dir() / "config.json"


def load_config() -> AppConfig:
    path = _config_file()
    if not path.is_file():
        return AppConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AppConfig(**data)
    except (json.JSONDecodeError, ValueError, OSError):
        return AppConfig()


def save_config(cfg: AppConfig) -> None:
    path = _config_file()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg.model_dump(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
