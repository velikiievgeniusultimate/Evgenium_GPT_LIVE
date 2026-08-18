from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

APP_NAME = "egl"
DEFAULT_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
DEFAULT_MODEL_DIRNAME = "vosk-model-small-ru-0.22"
DEFAULT_BROWSER_PROFILE_DIRNAME = "browser-profile-system"


def app_home() -> Path:
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
    # User-facing phrases remain canonical. hotword.py maps only truly OOV
    # tokens (such as invented «евгениум») to an explicit acoustic surrogate.
    wake_aliases: list[str] = field(default_factory=lambda: ["евгениум слушай"])
    stop_aliases: list[str] = field(default_factory=lambda: ["евгениум стоп"])
    # Wake is conservative: FINAL result + strong word-confidence floor.
    # Stop is intentionally permissive and may fire on partial recognition.
    wake_confidence_threshold: float = 0.86
    stop_confidence_threshold: float = 0.35
    vosk_model_url: str = DEFAULT_MODEL_URL
    vosk_model_path: str = ""
    browser_profile_path: str = ""
    # Runtime Chromium is always background/hidden and long-lived.
    browser_headless: bool = True
    browser_keep_alive: bool = True
    microphone_device: int | None = None
    # Per-EGL Chromium playback volume. 100 = normal; values above 100 use
    # PulseAudio/PipeWire software amplification and may introduce clipping.
    assistant_volume_percent: int = 100
    indicator_enabled: bool = True
    indicator_size: int = 74
    indicator_margin: int = 18

    @classmethod
    def default(cls) -> "EGLConfig":
        cfg = cls()
        cfg.vosk_model_path = str(data_dir() / "models" / DEFAULT_MODEL_DIRNAME)
        cfg.browser_profile_path = str(data_dir() / DEFAULT_BROWSER_PROFILE_DIRNAME)
        return cfg

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EGLConfig":
        defaults = asdict(cls.default())
        defaults.update(raw)
        defaults["browser_headless"] = True
        defaults["browser_keep_alive"] = True

        wake_phrase = str(defaults.get("wake_phrase") or "евгениум слушай")
        stop_phrase = str(defaults.get("stop_phrase") or "евгениум стоп")
        defaults["wake_aliases"] = [wake_phrase]
        defaults["stop_aliases"] = [stop_phrase]
        try:
            defaults["wake_confidence_threshold"] = min(
                0.99, max(0.0, float(defaults.get("wake_confidence_threshold", 0.86)))
            )
        except (TypeError, ValueError):
            defaults["wake_confidence_threshold"] = 0.86
        try:
            defaults["stop_confidence_threshold"] = min(
                0.99, max(0.0, float(defaults.get("stop_confidence_threshold", 0.35)))
            )
        except (TypeError, ValueError):
            defaults["stop_confidence_threshold"] = 0.35
        try:
            defaults["assistant_volume_percent"] = min(
                150, max(0, int(defaults.get("assistant_volume_percent", 100)))
            )
        except (TypeError, ValueError):
            defaults["assistant_volume_percent"] = 100
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
    cfg.browser_headless = True
    cfg.browser_keep_alive = True
    cfg.wake_aliases = [cfg.wake_phrase]
    cfg.stop_aliases = [cfg.stop_phrase]
    cfg.assistant_volume_percent = min(150, max(0, int(cfg.assistant_volume_percent)))
    path = config_path()
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(asdict(cfg), fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path
