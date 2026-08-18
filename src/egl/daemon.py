from __future__ import annotations

import logging
import queue
import signal
import threading
import time
from pathlib import Path

from .audio import OutputAudioMeter
from .browser import BrowserAutomationError, ChatGPTBrowser
from .config import load_config
from .control import ControlServer
from .hotword import HotwordListener
from .indicator_client import IndicatorClient
from .state import write_state

LOG = logging.getLogger(__name__)


def run_daemon() -> int:
    cfg = load_config()
    if not cfg.chat_url:
        raise RuntimeError("EGL is not configured. Run: egl setup")

    events: queue.Queue[str] = queue.Queue()
    stopping = threading.Event()

    def enqueue(command: str) -> None:
        events.put(command)

    def handle_signal(signum, frame):  # type: ignore[no-untyped-def]
        stopping.set()
        events.put("shutdown")

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    indicator = IndicatorClient(cfg.indicator_enabled, cfg.indicator_size, cfg.indicator_margin)
    meter = OutputAudioMeter()
    listener = HotwordListener(
        model_path=Path(cfg.vosk_model_path),
        wake_aliases=cfg.wake_aliases,
        stop_aliases=cfg.stop_aliases,
        on_wake=lambda: enqueue("wake"),
        on_stop=lambda: enqueue("stop"),
        microphone_device=cfg.microphone_device,
    )
    control = ControlServer(enqueue)
    voice_active = False

    write_state("starting", "launching browser")
    browser = ChatGPTBrowser(Path(cfg.browser_profile_path), cfg.chat_url, cfg.browser_headless)

    try:
        browser.open()
        listener.start()
        control.start()
        meter.start()
        write_state("idle", f'waiting for "{cfg.wake_phrase}"')
        LOG.info('EGL ready. Wake phrase: "%s"', cfg.wake_phrase)

        while not stopping.is_set():
            try:
                command = events.get(timeout=0.05)
            except queue.Empty:
                command = ""

            if command in {"wake", "start"} and not voice_active:
                write_state("starting_voice", "opening ChatGPT Voice")
                indicator.show("starting")
                try:
                    browser.start_voice()
                    voice_active = True
                    listener.set_voice_active(True)
                    indicator.send(mode="listening")
                    write_state("listening", f'waiting for "{cfg.stop_phrase}"')
                    LOG.info("ChatGPT Voice started")
                except BrowserAutomationError as exc:
                    LOG.error("Could not start voice: %s", exc)
                    indicator.send(mode="error")
                    write_state("error", str(exc))
                    time.sleep(1.2)
                    indicator.hide()
                    write_state("idle", f'waiting for "{cfg.wake_phrase}"')

            elif command in {"stop", "end"} and voice_active:
                write_state("stopping_voice", "closing ChatGPT Voice")
                listener.set_voice_active(False)
                try:
                    browser.stop_voice()
                except Exception:
                    LOG.exception("Voice stop fallback failed")
                voice_active = False
                indicator.hide()
                write_state("idle", f'waiting for "{cfg.wake_phrase}"')
                LOG.info("ChatGPT Voice stopped")

            elif command in {"shutdown", "quit"}:
                stopping.set()

            if voice_active:
                indicator.send(level=meter.level, mode="listening")

    finally:
        write_state("stopping")
        listener.set_voice_active(False)
        control.close()
        listener.close()
        meter.close()
        indicator.close()
        browser.close()
        write_state("offline")
    return 0
