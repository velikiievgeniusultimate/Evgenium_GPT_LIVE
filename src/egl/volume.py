from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
from typing import Any

LOG = logging.getLogger(__name__)


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


def _is_egl_stream(item: dict[str, Any], *, x11_display: str | None) -> bool:
    """Match only the Chromium playback stream owned by EGL's private Xvfb.

    Chromium overwrites PulseAudio's application.name, so an environment-level
    application-name tag is not reliable. PipeWire/PulseAudio does preserve the
    X11 display that owns the stream (`window.x11.display`). EGL gives its
    runtime Chromium a dedicated Xvfb display such as :90, making that display
    the strongest per-process identifier we have without touching unrelated
    Chromium/Discord/system audio.
    """
    if not x11_display:
        return False
    props = item.get("properties")
    if not isinstance(props, dict):
        return False
    return str(props.get("window.x11.display", "")) == x11_display


def set_assistant_volume(
    percent: int,
    *,
    x11_display: str | None,
    wait_seconds: float = 0.0,
) -> int:
    """Set playback volume for the sink-input on EGL's private Xvfb display."""
    pactl = _pactl()
    if pactl is None or not x11_display:
        return 0

    percent = min(150, max(0, int(percent)))
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while True:
        changed = 0
        for item in _sink_inputs():
            if not _is_egl_stream(item, x11_display=x11_display):
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


def schedule_assistant_volume(
    percent: int,
    *,
    x11_display: str | None,
    wait_seconds: float = 2.5,
) -> None:
    """Apply volume asynchronously so wake/start latency is never blocked."""

    def worker() -> None:
        changed = set_assistant_volume(
            percent,
            x11_display=x11_display,
            wait_seconds=wait_seconds,
        )
        LOG.info(
            "Assistant volume applied: %d%% to %d stream(s) on X display %s",
            percent,
            changed,
            x11_display,
        )

    threading.Thread(target=worker, name="egl-volume", daemon=True).start()
