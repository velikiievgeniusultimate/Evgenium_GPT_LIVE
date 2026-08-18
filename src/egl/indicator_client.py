from __future__ import annotations

import json
import logging
import subprocess
import sys
from typing import TextIO

LOG = logging.getLogger(__name__)


class IndicatorClient:
    def __init__(self, enabled: bool, size: int, margin: int) -> None:
        self.enabled = enabled
        self.size = size
        self.margin = margin
        self._proc: subprocess.Popen[str] | None = None
        self._stdin: TextIO | None = None

    def show(self, mode: str = "listening") -> None:
        if not self.enabled:
            return
        if not self._proc or self._proc.poll() is not None:
            try:
                self._proc = subprocess.Popen(
                    [sys.executable, "-m", "egl.indicator", "--size", str(self.size), "--margin", str(self.margin)],
                    stdin=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
                self._stdin = self._proc.stdin
            except Exception:
                LOG.exception("Could not start indicator")
                return
        self.send(mode=mode, level=0.0)

    def send(self, **payload) -> None:  # type: ignore[no-untyped-def]
        if not self._stdin:
            return
        try:
            self._stdin.write(json.dumps(payload) + "\n")
            self._stdin.flush()
        except (BrokenPipeError, OSError):
            self._stdin = None

    def hide(self) -> None:
        if self._proc and self._proc.poll() is None:
            self.send(quit=True)
            try:
                self._proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._proc.terminate()
        self._proc = None
        self._stdin = None

    def close(self) -> None:
        self.hide()
