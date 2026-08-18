from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

APP_NAME = "egl"
DEFAULT_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
DEFAULT_MODEL_DIRNAME = "vosk-model-small-ru-0.22"


def app_home() -> Path:
    """Return EGL's main home directory.

    EGL intentionally keeps almost all persistent project/runtime data in one
    visible directory so installation, backup and removal are predictable.
    """
    return Path(os.environ.get("EGL_HOME", str(Path.home() / "Evgenium_GPT"))).expanduser()


def config_dir() -> Path:
    return app_home() / "config"


def data_dir() -> Path:
    return app_home() / "data"


def state_dir() -> Path:
    return app_home() / "state"


def runtime_dir() -> Path:
    raw = os.environ.get("XDG_RUNTIME_DIR")
    if raw:
        return Path(raw) / APP_NAME
    return state_dir() / "run"


@dataclass(slots=True)
class EGLConfig:
    chat_url: str = ""
    wake_phrase: str = "евгениум слушай"
    stop_phrase: str = "евгениум стоп"
    wake_aliases: list[str] = field(default_factory=lambda: [
        "евгениум слушай",
        "евгений слушай",
        "евгениум слушает",
    ])
    stop_aliases: list[str] = field(default_factory=lambda: [
        "евгениум стоп",
        "евгений стоп",
    ])
    vosk_model_url: str = DEFAULT_MODEL_URL
    vosk_model_path: str = ""
    browser_profile_path: str = ""
    browser_headless: bool = True
    microphone_device: int | None = None
    indicator_enabled: bool = True
    indicator_size: int = 74
    indicator_margin: int = 18

    @classmethod
    def default(cls) -> "EGLConfig":
        cfg = cls()
        cfg.vosk_model_path = str(data_dir() / "models" / DEFAULT_MODEL_DIRNAME)
        cfg.browser_profile_path = str(data_dir() / "browser-profile")
        return cfg

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EGLConfig":
        defaults = asdict(cls.default())
        defaults.update(raw)
        return cls(**defaults)


def config_path() -> Path:
    return config_dir() / "config.json"


def ensure_dirs() -> None:
    for path in (config_dir(), data_dir(), state_dir(), runtime_dir()):
        path.mkdir(parents=True, exist_ok=True)


def load_config() -> EGLConfig:
    path = config_path()
    if not path.exists():
        return EGLConfig.default()
    with path.open("r", encoding="utf-8") as fh:
        return EGLConfig.from_dict(json.load(fh))


def save_config(cfg: EGLConfig) -> Path:
    ensure_dirs()
    path = config_path()
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(asdict(cfg), fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path
