from __future__ import annotations

import logging
import queue
import shutil
import signal
import subprocess
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


def _notify(summary: str, body: str) -> None:
    if shutil.which("notify-send"):
        subprocess.Popen(
            ["notify-send", "-a", "EGL", summary, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


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
    browser: ChatGPTBrowser | None = None

    def close_browser() -> None:
        nonlocal browser
        if browser is not None:
            try:
                browser.close()
            except Exception:
                LOG.exception("Could not close EGL browser cleanly")
        browser = None

    def ensure_browser() -> ChatGPTBrowser:
        nonlocal browser
        if browser is not None and browser.is_running():
            return browser
        close_browser()
        browser = ChatGPTBrowser(
            Path(cfg.browser_profile_path),
            cfg.chat_url,
            cfg.browser_headless,
        )
        browser.open()
        return browser

    # Deliberately start only local pieces here. Chromium is lazy-launched on
    # wake. This makes boot independent of internet/VPN availability and avoids
    # any browser window/process until the assistant is actually requested.
    listener.start()
    control.start()
    meter.start()
    write_state("idle", f'waiting for "{cfg.wake_phrase}"')
    LOG.info('EGL ready without browser. Wake phrase: "%s"', cfg.wake_phrase)

    try:
        while not stopping.is_set():
            try:
                command = events.get(timeout=0.05)
            except queue.Empty:
                command = ""

            if command in {"wake", "start"} and not voice_active:
                write_state("starting_voice", "opening ChatGPT Voice")
                indicator.show("starting")
                try:
                    current = ensure_browser()
                    current.start_voice()
                    voice_active = True
                    listener.set_voice_active(True)
                    indicator.send(mode="listening")
                    write_state("listening", f'waiting for "{cfg.stop_phrase}"')
                    LOG.info("ChatGPT Voice started")
                except Exception as exc:
                    LOG.error("Could not start ChatGPT Voice: %s", exc, exc_info=True)
                    close_browser()
                    voice_active = False
                    listener.set_voice_active(False)
                    indicator.send(mode="error")
                    write_state("error", str(exc))
                    _notify(
                        "EGL не смог открыть ChatGPT",
                        "Проверь VPN/сеть. EGL не будет повторять попытку сам — скажи «Евгениум слушай» ещё раз.",
                    )
                    time.sleep(1.5)
                    indicator.hide()
                    write_state("idle", f'waiting for "{cfg.wake_phrase}"')

            elif command in {"stop", "end"} and voice_active:
                write_state("stopping_voice", "closing ChatGPT Voice")
                listener.set_voice_active(False)
                try:
                    if browser is not None:
                        browser.stop_voice()
                except Exception:
                    LOG.exception("Voice stop fallback failed")
                voice_active = False
                indicator.hide()
                if not cfg.browser_keep_alive:
                    close_browser()
                write_state("idle", f'waiting for "{cfg.wake_phrase}"')
                LOG.info("ChatGPT Voice stopped")

            elif command == "browser_show":
                try:
                    current = ensure_browser()
                    current.show_window()
                    write_state("browser_visible", "service browser shown by user")
                except Exception as exc:
                    LOG.error("Could not show browser: %s", exc, exc_info=True)
                    write_state("error", str(exc))
                    _notify("EGL", f"Не удалось показать браузер: {exc}")

            elif command == "browser_hide":
                try:
                    if browser is not None and browser.is_running():
                        browser.hide_window()
                    write_state(
                        "listening" if voice_active else "idle",
                        f'waiting for "{cfg.stop_phrase if voice_active else cfg.wake_phrase}"',
                    )
                except Exception as exc:
                    LOG.error("Could not hide browser: %s", exc, exc_info=True)

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
        close_browser()
        write_state("offline")
    return 0
