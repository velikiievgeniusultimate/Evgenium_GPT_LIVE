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
    # 0.5.2 deliberately removed the old soft aliases ("евгений слушай",
    # "евгениум слушает", ...). Wake must be the exact canonical phrase.
    wake_aliases: list[str] = field(default_factory=lambda: ["евгениум слушай"])
    stop_aliases: list[str] = field(default_factory=lambda: ["евгениум стоп"])
    # Wake is conservative: only a FINAL Vosk result with every decoded word
    # above this confidence may trigger it. Stop is intentionally much more
    # permissive and is allowed on partial recognition while Voice is active.
    wake_confidence_threshold: float = 0.86
    stop_confidence_threshold: float = 0.35
    vosk_model_url: str = DEFAULT_MODEL_URL
    vosk_model_path: str = ""
    browser_profile_path: str = ""
    # Kept in config for backward compatibility with 0.4. EGL 0.5 enforces
    # both values: runtime Chromium is always background/hidden and long-lived.
    browser_headless: bool = True
    browser_keep_alive: bool = True
    microphone_device: int | None = None
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
        # Migrate old 0.4/0.5 user choices to the fixed runtime invariants.
        defaults["browser_headless"] = True
        defaults["browser_keep_alive"] = True
        # Security/reliability migration: old soft aliases were a major source
        # of accidental wake-ups. The configured phrases are now canonical.
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
    # Persist only the canonical phrases. Aliases are deliberately not a user
    # escape hatch anymore because they make wake detection much softer.
    cfg.wake_aliases = [cfg.wake_phrase]
    cfg.stop_aliases = [cfg.stop_phrase]
    path = config_path()
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(asdict(cfg), fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path
