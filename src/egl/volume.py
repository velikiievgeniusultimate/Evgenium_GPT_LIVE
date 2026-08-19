from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
import time
from typing import Any

LOG = logging.getLogger(__name__)

EGL_XVFB_DISPLAY_RE = re.compile(r"^:(9[0-9]|1[0-5][0-9])$")


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


def _is_private_egl_chromium(props: dict[str, Any]) -> bool:
    display = str(props.get("window.x11.display", ""))
    binary = str(props.get("application.process.binary", "")).lower()
    role = str(props.get("media.role", "")).lower()
    return bool(
        EGL_XVFB_DISPLAY_RE.fullmatch(display)
        and "chrom" in binary
        and role == "phone"
    )


def _is_egl_stream(item: dict[str, Any], *, x11_display: str | None) -> bool:
    """Match only EGL's hidden Chromium playback sink-input.

    The live PipeWire properties observed on Arch/KDE are:
      application.process.binary=chromium
      media.role=phone
      window.x11.display=:90

    The daemon knows the exact private display and passes it explicitly. The GUI
    is a separate process, so when it has no display value it safely falls back
    to EGL's reserved Xvfb range (:90..:159) plus Chromium+phone constraints.
    Normal desktop Chromium/Discord streams on displays such as :0/:1 are not
    matched.
    """
    props = item.get("properties")
    if not isinstance(props, dict):
        return False

    display = str(props.get("window.x11.display", ""))
    if x11_display:
        return display == x11_display
    return _is_private_egl_chromium(props)


def set_assistant_volume(
    percent: int,
    *,
    x11_display: str | None = None,
    wait_seconds: float = 0.0,
) -> int:
    """Set playback volume for EGL's hidden Chromium sink-input only."""
    pactl = _pactl()
    if pactl is None:
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
    x11_display: str | None = None,
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
            x11_display or "auto",
        )

    threading.Thread(target=worker, name="egl-volume", daemon=True).start()
