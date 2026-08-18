from __future__ import annotations

import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Callable

from .phrases import phrase_matches

LOG = logging.getLogger(__name__)


class HotwordListener:
    """Offline, grammar-limited Russian phrase detector using Vosk."""

    def __init__(
        self,
        model_path: Path,
        wake_aliases: list[str],
        stop_aliases: list[str],
        on_wake: Callable[[], None],
        on_stop: Callable[[], None],
        microphone_device: int | None = None,
        on_debug: Callable[[str, bool, bool, bool], None] | None = None,
    ) -> None:
        self.model_path = model_path
        self.wake_aliases = wake_aliases
        self.stop_aliases = stop_aliases
        self.on_wake = on_wake
        self.on_stop = on_stop
        self.microphone_device = microphone_device
        self.on_debug = on_debug
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._active = threading.Event()
        # Wake and stop need independent debounce clocks. A stop spoken soon
        # after wake must never be suppressed by the wake trigger itself.
        self._last_wake_trigger = 0.0
        self._last_stop_trigger = 0.0
        self._last_debug_text = ""

    def set_voice_active(self, active: bool) -> None:
        if active:
            self._active.set()
        else:
            self._active.clear()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="egl-hotword", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _dispatch(self, text: str) -> None:
        active = self._active.is_set()
        wake_match = phrase_matches(text, self.wake_aliases)
        stop_match = phrase_matches(text, self.stop_aliases)

        if self.on_debug is not None and text != self._last_debug_text:
            self._last_debug_text = text
            try:
                self.on_debug(text, active, wake_match, stop_match)
            except Exception:
                LOG.debug("Hotword debug callback failed", exc_info=True)

        now = time.monotonic()
        if active:
            if stop_match and now - self._last_stop_trigger >= 1.2:
                self._last_stop_trigger = now
                self.on_stop()
        elif wake_match and now - self._last_wake_trigger >= 1.5:
            self._last_wake_trigger = now
            self.on_wake()

    def _run(self) -> None:
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model, SetLogLevel

            SetLogLevel(-1)
            model = Model(str(self.model_path))
            grammar = sorted(set(self.wake_aliases + self.stop_aliases + ["[unk]"]))
        except Exception:
            LOG.exception("Hotword engine initialization failed")
            return

        retry_delay = 2.0
        while not self._stop.is_set():
            try:
                recognizer = KaldiRecognizer(model, 16000, json.dumps(grammar, ensure_ascii=False))
                audio_q: queue.Queue[bytes] = queue.Queue(maxsize=12)

                def callback(indata, frames, time_info, status):  # type: ignore[no-untyped-def]
                    if status:
                        LOG.debug("Microphone status: %s", status)
                    try:
                        audio_q.put_nowait(bytes(indata))
                    except queue.Full:
                        pass

                with sd.RawInputStream(
                    samplerate=16000,
                    blocksize=4000,
                    dtype="int16",
                    channels=1,
                    device=self.microphone_device,
                    callback=callback,
                ):
                    LOG.info("Hotword listener ready (device=%s)", self.microphone_device)
                    retry_delay = 2.0
                    while not self._stop.is_set():
                        try:
                            chunk = audio_q.get(timeout=0.25)
                        except queue.Empty:
                            continue
                        if recognizer.AcceptWaveform(chunk):
                            text = json.loads(recognizer.Result()).get("text", "")
                            if text:
                                self._dispatch(text)
                        else:
                            partial = json.loads(recognizer.PartialResult()).get("partial", "")
                            if partial:
                                self._dispatch(partial)
            except Exception:
                LOG.exception(
                    "Hotword audio stream failed; retrying in %.0f seconds",
                    retry_delay,
                )
                if self._stop.wait(retry_delay):
                    break
                retry_delay = min(retry_delay * 2.0, 30.0)
