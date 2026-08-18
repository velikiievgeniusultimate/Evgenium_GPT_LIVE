from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
from typing import Any

LOG = logging.getLogger(__name__)

EGL_AUDIO_APP_NAME = "Evgenium GPT LIVE Voice"


def _pactl() -> str | None:
    return shutil.which("pactl")


def _sink_inputs() -> list[dict[str, Any]]:
    pactl = _pactl()
    if pactl is None:
        return []
    proc = subprocess.run(
        [pactl, "-f", "json", "list", "sink-inputs"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        LOG.debug("pactl sink-input query failed: %s", proc.stderr.strip())
        return []
    try:
        payload = json.loads(proc.stdout or "[]")
    except ValueError:
        LOG.debug("pactl returned invalid JSON")
        return []
    return payload if isinstance(payload, list) else []


def _is_egl_stream(item: dict[str, Any]) -> bool:
    props = item.get("properties")
    if not isinstance(props, dict):
        return False
    name = str(props.get("application.name", ""))
    return name == EGL_AUDIO_APP_NAME


def set_assistant_volume(percent: int, *, wait_seconds: float = 0.0) -> int:
    """Set playback volume for EGL Chromium streams only.

    Returns the number of sink-input streams changed. A short wait can be used
    right after Voice starts because Chromium may create its audio stream a few
    hundred milliseconds after the Voice UI becomes active.
    """
    pactl = _pactl()
    if pactl is None:
        return 0

    percent = min(150, max(0, int(percent)))
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while True:
        changed = 0
        for item in _sink_inputs():
            if not _is_egl_stream(item):
                continue
            try:
                index = int(item["index"])
            except (KeyError, TypeError, ValueError):
                continue
            proc = subprocess.run(
                [pactl, "set-sink-input-volume", str(index), f"{percent}%"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if proc.returncode == 0:
                changed += 1

        if changed or time.monotonic() >= deadline:
            return changed
        time.sleep(0.12)


def schedule_assistant_volume(percent: int, *, wait_seconds: float = 2.5) -> None:
    """Apply volume asynchronously so wake/start latency is never blocked."""

    def worker() -> None:
        changed = set_assistant_volume(percent, wait_seconds=wait_seconds)
        LOG.info("Assistant volume applied: %d%% to %d stream(s)", percent, changed)

    threading.Thread(target=worker, name="egl-volume", daemon=True).start()
