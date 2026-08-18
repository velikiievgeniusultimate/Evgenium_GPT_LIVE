from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import ensure_dirs, state_dir


@dataclass(slots=True)
class RuntimeState:
    mode: str = "idle"
    detail: str = ""
    updated_at: float = 0.0


def state_path() -> Path:
    return state_dir() / "state.json"


def write_state(mode: str, detail: str = "") -> None:
    ensure_dirs()
    payload = RuntimeState(mode=mode, detail=detail, updated_at=time.time())
    path = state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(payload), ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_state() -> RuntimeState:
    try:
        raw = json.loads(state_path().read_text(encoding="utf-8"))
        return RuntimeState(**raw)
    except (OSError, ValueError, TypeError):
        return RuntimeState(mode="offline", detail="daemon state unavailable", updated_at=0.0)
