from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import ensure_dirs, state_dir


@dataclass(slots=True)
class RuntimeState:
    mode: str = "idle"
    detail: str = ""
    updated_at: float = 0.0


def state_path() -> Path:
    return state_dir() / "state.json"


def debug_log_path() -> Path:
    return state_dir() / "debug.jsonl"


def debug_screenshot_path() -> Path:
    return state_dir() / "debug-browser.png"


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


def append_debug_event(event: str, detail: str = "", **data: Any) -> None:
    """Append one structured diagnostic event and keep the file bounded.

    The GUI reads this file directly, so debugging does not depend on journalctl
    access and remains useful even when the daemon is otherwise healthy.
    """
    ensure_dirs()
    path = debug_log_path()
    payload: dict[str, Any] = {
        "ts": time.time(),
        "event": event,
        "detail": detail,
    }
    payload.update(data)
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        # Keep roughly the latest 300 events. This is intentionally simple and
        # only runs when the log grows beyond a small threshold.
        if path.stat().st_size > 256_000:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            path.write_text("\n".join(lines[-300:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def read_debug_events(limit: int = 120) -> list[dict[str, Any]]:
    try:
        lines = debug_log_path().read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    result: list[dict[str, Any]] = []
    for line in lines[-max(1, limit):]:
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                result.append(item)
        except ValueError:
            continue
    return result
