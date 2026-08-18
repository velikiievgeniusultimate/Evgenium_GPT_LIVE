from __future__ import annotations

import array
import logging
import math
import shutil
import subprocess
import threading

LOG = logging.getLogger(__name__)


class OutputAudioMeter:
    """Best-effort RMS meter for the default PulseAudio/PipeWire output monitor."""

    def __init__(self) -> None:
        self.level = 0.0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.available = bool(shutil.which("pactl") and shutil.which("parec"))

    def start(self) -> None:
        if not self.available or (self._thread and self._thread.is_alive()):
            return
        self._thread = threading.Thread(target=self._run, name="egl-output-meter", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    @staticmethod
    def _rms(data: bytes) -> float:
        samples = array.array("h")
        samples.frombytes(data)
        if not samples:
            return 0.0
        energy = sum(sample * sample for sample in samples) / len(samples)
        rms = math.sqrt(energy) / 32768.0
        return min(1.0, rms * 7.0)

    def _run(self) -> None:
        try:
            sink = subprocess.check_output(
                ["pactl", "get-default-sink"], text=True, timeout=2
            ).strip()
            monitor = f"{sink}.monitor"
            proc = subprocess.Popen(
                [
                    "parec",
                    "--device", monitor,
                    "--format=s16le",
                    "--rate=16000",
                    "--channels=1",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            assert proc.stdout is not None
            try:
                while not self._stop.is_set():
                    data = proc.stdout.read(1600)
                    if not data:
                        break
                    measured = self._rms(data)
                    self.level = max(measured, self.level * 0.68)
            finally:
                proc.terminate()
        except Exception:
            self.available = False
            LOG.exception("Output audio meter unavailable; indicator will use idle breathing")
