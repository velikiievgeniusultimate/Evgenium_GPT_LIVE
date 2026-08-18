from __future__ import annotations

import logging
import os
import socket
import threading
from pathlib import Path
from typing import Callable

from .config import ensure_dirs, runtime_dir

LOG = logging.getLogger(__name__)


def socket_path() -> Path:
    return runtime_dir() / "control.sock"


class ControlServer:
    def __init__(self, on_command: Callable[[str], None]) -> None:
        self.on_command = on_command
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._sock: socket.socket | None = None

    def start(self) -> None:
        ensure_dirs()
        path = socket_path()
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._sock.bind(str(path))
        os.chmod(path, 0o600)
        self._sock.settimeout(0.5)
        self._thread = threading.Thread(target=self._run, name="egl-control", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                data = self._sock.recv(128)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                self.on_command(data.decode("utf-8").strip())
            except Exception:
                LOG.exception("Control command failed")

    def close(self) -> None:
        self._stop.set()
        if self._sock:
            self._sock.close()
        if self._thread:
            self._thread.join(timeout=1)
        try:
            socket_path().unlink()
        except FileNotFoundError:
            pass


def send_command(command: str) -> None:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.sendto(command.encode("utf-8"), str(socket_path()))
    finally:
        sock.close()
