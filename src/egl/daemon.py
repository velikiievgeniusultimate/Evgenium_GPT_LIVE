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
from .browser import ChatGPTBrowser
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
    browser_ready = False
    browser: ChatGPTBrowser | None = None
    browser_restart_backoff = 10.0
    page_refresh_backoff = 10.0
    next_browser_restart = 0.0
    next_page_refresh = 0.0

    def idle_state() -> None:
        if browser_ready:
            write_state("idle_ready", f'ChatGPT ready; waiting for "{cfg.wake_phrase}"')
        elif browser is not None and browser.is_running():
            write_state("idle_loading", f'ChatGPT tab open; waiting for network/VPN and "{cfg.wake_phrase}"')
        else:
            write_state("idle_recovering", f'browser recovery; waiting for "{cfg.wake_phrase}"')

    def close_browser() -> None:
        nonlocal browser, browser_ready
        if browser is not None:
            try:
                browser.close()
            except Exception:
                LOG.exception("Could not close EGL browser cleanly")
        browser = None
        browser_ready = False

    def start_permanent_browser() -> bool:
        """Start one invisible, long-lived Chromium instance.

        Network/VPN failure is not a browser failure. open_runtime() deliberately
        keeps Chromium/Xvfb/CDP alive even when ChatGPT itself is not reachable.
        """
        nonlocal browser, browser_ready, browser_restart_backoff, page_refresh_backoff
        close_browser()
        browser = ChatGPTBrowser(
            Path(cfg.browser_profile_path),
            cfg.chat_url,
            headless=True,
            virtual_display=True,
        )
        browser_ready = browser.open_runtime()
        browser_restart_backoff = 10.0
        page_refresh_backoff = 10.0
        LOG.info("Permanent hidden Chromium started; ChatGPT ready=%s", browser_ready)
        return browser_ready

    # Local controls/hotword must become available even if the network is down.
    listener.start()
    control.start()
    meter.start()

    # Unlike EGL 0.4, runtime Chromium is intentionally started immediately and
    # then kept alive for the whole daemon lifetime. Its window lives on Xvfb,
    # so Plasma never sees it.
    write_state("starting_browser", "starting permanent hidden ChatGPT tab")
    try:
        start_permanent_browser()
    except Exception as exc:
        LOG.error("Initial hidden browser startup failed: %s", exc, exc_info=True)
        close_browser()
        next_browser_restart = time.monotonic() + browser_restart_backoff
        browser_restart_backoff = min(browser_restart_backoff * 1.8, 60.0)
    idle_state()
    LOG.info('EGL ready. Wake phrase: "%s"', cfg.wake_phrase)

    try:
        while not stopping.is_set():
            try:
                command = events.get(timeout=0.05)
            except queue.Empty:
                command = ""

            now = time.monotonic()

            # Browser process resilience: a genuine Chromium/Xvfb crash gets a
            # bounded restart loop. Missing VPN does NOT restart the process.
            if not voice_active and (browser is None or not browser.is_running()):
                if now >= next_browser_restart:
                    try:
                        start_permanent_browser()
                        next_page_refresh = now + 2.0
                        idle_state()
                    except Exception as exc:
                        LOG.error("Hidden browser recovery failed: %s", exc, exc_info=True)
                        close_browser()
                        next_browser_restart = now + browser_restart_backoff
                        browser_restart_backoff = min(browser_restart_backoff * 1.8, 60.0)
                        idle_state()

            # Page readiness resilience: keep the same browser/tab alive and
            # gently refresh it until ChatGPT/Voice becomes available. This is
            # what recovers automatically when VPN is enabled after login.
            if (
                not voice_active
                and browser is not None
                and browser.is_running()
                and not browser_ready
                and now >= next_page_refresh
            ):
                try:
                    browser_ready = browser.reload_chat(timeout_ms=8_000)
                except Exception as exc:
                    LOG.debug("Background ChatGPT readiness check failed: %s", exc, exc_info=True)
                    browser_ready = False
                if browser_ready:
                    LOG.info("Hidden ChatGPT tab is ready")
                    page_refresh_backoff = 10.0
                    idle_state()
                else:
                    next_page_refresh = now + page_refresh_backoff
                    page_refresh_backoff = min(page_refresh_backoff * 1.5, 60.0)

            if command in {"wake", "start"} and not voice_active:
                write_state("starting_voice", "using preloaded ChatGPT tab")
                indicator.show("starting")
                try:
                    if browser is None or not browser.is_running():
                        start_permanent_browser()

                    assert browser is not None
                    if not browser_ready:
                        # Explicit wake gets one immediate, generous readiness
                        # attempt. The browser process/tab itself is not replaced.
                        browser_ready = browser.reload_chat(timeout_ms=20_000)
                    if not browser_ready:
                        raise RuntimeError(
                            "Hidden ChatGPT tab is running but Voice is not ready; check VPN/network/login"
                        )

                    browser.start_voice()
                    voice_active = True
                    listener.set_voice_active(True)
                    indicator.send(mode="listening")
                    write_state("listening", f'waiting for "{cfg.stop_phrase}"')
                    LOG.info("ChatGPT Voice started from preloaded tab")
                except Exception as exc:
                    LOG.error("Could not start ChatGPT Voice: %s", exc, exc_info=True)
                    voice_active = False
                    listener.set_voice_active(False)
                    browser_ready = bool(browser and browser.is_running() and browser.has_voice_button())
                    indicator.send(mode="error")
                    write_state("error", str(exc))
                    _notify(
                        "EGL: ChatGPT пока не готов",
                        "Скрытая вкладка остаётся запущенной. Проверь VPN/сеть; EGL сам продолжит готовить её в фоне.",
                    )
                    time.sleep(1.2)
                    indicator.hide()
                    next_page_refresh = time.monotonic() + 3.0
                    idle_state()

            elif command in {"stop", "end"} and voice_active:
                write_state("stopping_voice", "closing Voice; keeping ChatGPT tab alive")
                listener.set_voice_active(False)
                try:
                    if browser is not None:
                        browser.stop_voice()
                except Exception:
                    LOG.exception("Voice stop fallback failed")
                voice_active = False
                indicator.hide()
                # The core invariant of EGL 0.5: never close the runtime browser
                # after a conversation. Keep the same loaded tab warm.
                browser_ready = bool(browser and browser.is_running() and browser.ensure_chat_ready(timeout_ms=5_000))
                if not browser_ready:
                    next_page_refresh = time.monotonic() + 2.0
                idle_state()
                LOG.info("ChatGPT Voice stopped; permanent tab kept alive")

            elif command == "browser_reload":
                try:
                    if browser is None or not browser.is_running():
                        start_permanent_browser()
                    assert browser is not None
                    browser_ready = browser.reload_chat(timeout_ms=20_000)
                    idle_state()
                except Exception as exc:
                    LOG.error("Could not reload hidden ChatGPT tab: %s", exc, exc_info=True)
                    browser_ready = False
                    next_page_refresh = time.monotonic() + 5.0
                    idle_state()

            elif command in {"browser_show", "browser_hide"}:
                # Compatibility with EGL 0.4 commands. Runtime now lives on a
                # private X display and intentionally cannot be exposed to Plasma.
                _notify(
                    "EGL",
                    "Служебный Chromium работает на приватном виртуальном дисплее и всегда невидим.",
                )

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
