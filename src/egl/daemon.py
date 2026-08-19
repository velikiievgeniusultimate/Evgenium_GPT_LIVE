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
from .state import append_debug_event, debug_screenshot_path, write_state
from .volume import set_assistant_volume

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

    def hotword_debug(observation: dict[str, object]) -> None:
        payload = dict(observation)
        text = str(payload.pop("text", ""))
        append_debug_event("hotword_heard", text, **payload)

    def wake_detected() -> None:
        append_debug_event("WAKE_ACCEPTED", cfg.wake_phrase)
        enqueue("wake")

    def stop_detected() -> None:
        append_debug_event("STOP_DETECTED", cfg.stop_phrase)
        enqueue("stop")

    listener = HotwordListener(
        model_path=Path(cfg.vosk_model_path),
        wake_aliases=cfg.wake_aliases,
        stop_aliases=cfg.stop_aliases,
        on_wake=wake_detected,
        on_stop=stop_detected,
        microphone_device=cfg.microphone_device,
        on_debug=hotword_debug,
        wake_confidence_threshold=cfg.wake_confidence_threshold,
        stop_confidence_threshold=cfg.stop_confidence_threshold,
    )
    control = ControlServer(enqueue)

    voice_active = False
    browser_ready = False
    browser: ChatGPTBrowser | None = None
    browser_restart_backoff = 10.0
    page_refresh_backoff = 10.0
    next_browser_restart = 0.0
    next_page_refresh = 0.0

    # Playback streams are not guaranteed to exist when Voice UI opens. Chromium
    # may create its PipeWire/Pulse sink-input only when GPT actually starts
    # speaking, which can happen many seconds later. Keep a desired volume in
    # daemon state and continuously enforce it for the whole Voice session.
    assistant_volume_target = cfg.assistant_volume_percent
    next_volume_enforce = 0.0
    volume_stream_present = False

    def browser_display() -> str | None:
        # ChatGPTBrowser owns the private Xvfb display. PipeWire exposes the
        # same value as window.x11.display on Chromium's sink-input.
        if browser is None:
            return None
        value = getattr(browser, "_display", None)
        return str(value) if value else None

    def snapshot(reason: str, *, log_success: bool = True) -> None:
        if browser is None or not browser.is_running():
            if log_success:
                append_debug_event("snapshot_skipped", reason, browser_running=False)
            return
        try:
            path = browser.capture_screenshot(debug_screenshot_path())
            if log_success:
                append_debug_event("snapshot", reason, path=str(path))
        except Exception as exc:
            append_debug_event("snapshot_failed", reason, error=str(exc))

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
        append_debug_event(
            "browser_started",
            "permanent hidden Chromium",
            ready=browser_ready,
            x11_display=browser_display(),
        )
        LOG.info(
            "Permanent hidden Chromium started; ChatGPT ready=%s display=%s",
            browser_ready,
            browser_display(),
        )
        return browser_ready

    listener.start()
    control.start()
    meter.start()
    append_debug_event(
        "daemon_started",
        "EGL daemon started",
        microphone=cfg.microphone_device,
        wake_threshold=cfg.wake_confidence_threshold,
        stop_threshold=cfg.stop_confidence_threshold,
        assistant_volume=assistant_volume_target,
        wake_aliases=cfg.wake_aliases,
        stop_aliases=cfg.stop_aliases,
    )

    write_state("starting_browser", "starting permanent hidden ChatGPT tab")
    try:
        start_permanent_browser()
    except Exception as exc:
        LOG.error("Initial hidden browser startup failed: %s", exc, exc_info=True)
        append_debug_event("browser_start_failed", str(exc))
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

            if not voice_active and (browser is None or not browser.is_running()):
                if now >= next_browser_restart:
                    try:
                        start_permanent_browser()
                        next_page_refresh = now + 2.0
                        idle_state()
                    except Exception as exc:
                        LOG.error("Hidden browser recovery failed: %s", exc, exc_info=True)
                        append_debug_event("browser_recovery_failed", str(exc))
                        close_browser()
                        next_browser_restart = now + browser_restart_backoff
                        browser_restart_backoff = min(browser_restart_backoff * 1.8, 60.0)
                        idle_state()

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
                    append_debug_event("chat_ready", "hidden ChatGPT tab became ready")
                    LOG.info("Hidden ChatGPT tab is ready")
                    page_refresh_backoff = 10.0
                    idle_state()
                else:
                    next_page_refresh = now + page_refresh_backoff
                    page_refresh_backoff = min(page_refresh_backoff * 1.5, 60.0)

            if command and command != "debug_snapshot_quiet":
                append_debug_event(
                    "command_received",
                    command,
                    voice_active=voice_active,
                    browser_ready=browser_ready,
                )

            if command in {"wake", "start"} and not voice_active:
                write_state("starting_voice", "using preloaded ChatGPT tab")
                indicator.show("starting")
                append_debug_event("voice_start_begin", "wake/start command accepted")
                try:
                    if browser is None or not browser.is_running():
                        start_permanent_browser()

                    assert browser is not None
                    if not browser_ready:
                        browser_ready = browser.reload_chat(timeout_ms=20_000)
                    if not browser_ready:
                        raise RuntimeError(
                            "Hidden ChatGPT tab is running but Voice is not ready; check VPN/network/login"
                        )

                    browser.start_voice()
                    voice_active = True
                    listener.set_voice_active(True)
                    next_volume_enforce = 0.0
                    volume_stream_present = False
                    indicator.send(mode="listening")
                    write_state("listening", f'waiting for "{cfg.stop_phrase}"')
                    append_debug_event(
                        "voice_started",
                        "Voice start click completed",
                        exit_button_visible=browser.is_voice_active_ui(),
                        assistant_volume=assistant_volume_target,
                        x11_display=browser_display(),
                    )
                    snapshot("after_voice_start")
                    LOG.info("ChatGPT Voice started from preloaded tab")
                except Exception as exc:
                    LOG.error("Could not start ChatGPT Voice: %s", exc, exc_info=True)
                    append_debug_event("voice_start_failed", str(exc))
                    voice_active = False
                    listener.set_voice_active(False)
                    browser_ready = bool(browser and browser.is_running() and browser.has_voice_button())
                    indicator.send(mode="error")
                    write_state("error", str(exc))
                    snapshot("voice_start_failed")
                    _notify(
                        "EGL: ChatGPT пока не готов",
                        "Скрытая вкладка остаётся запущенной. Проверь VPN/сеть; EGL сам продолжит готовить её в фоне.",
                    )
                    time.sleep(1.2)
                    indicator.hide()
                    next_page_refresh = time.monotonic() + 3.0
                    idle_state()

            elif command in {"stop", "end"}:
                stop_started = time.monotonic()
                indicator.hide()
                write_state("STOP_KILLING", "STOP accepted — terminating Voice now")
                ui_before = bool(browser and browser.is_voice_active_ui())
                append_debug_event(
                    "STOP_SENT",
                    "stop/end command accepted by daemon",
                    internal_voice_active=voice_active,
                    ui_active_before=ui_before,
                )
                listener.set_voice_active(False)

                verified = True
                method = "no_browser"
                browser_elapsed_ms = 0
                try:
                    if browser is not None:
                        verified = browser.stop_voice()
                        method = browser.last_stop_method
                        browser_elapsed_ms = browser.last_stop_elapsed_ms
                except Exception as exc:
                    verified = False
                    method = "exception"
                    LOG.exception("Aggressive Voice stop failed")
                    append_debug_event("STOP_EXCEPTION", str(exc))

                voice_active = False
                volume_stream_present = False
                next_volume_enforce = 0.0
                ui_after = bool(browser and browser.is_voice_active_ui())
                browser_ready = bool(browser and browser.is_running() and browser.has_voice_button())
                total_elapsed_ms = int((time.monotonic() - stop_started) * 1000)

                append_debug_event(
                    "STOP_CONFIRMED" if verified and not ui_after else "STOP_FAILED",
                    "Voice termination verification finished",
                    verified=verified,
                    stop_method=method,
                    browser_stop_ms=browser_elapsed_ms,
                    total_stop_ms=total_elapsed_ms,
                    ui_active_after=ui_after,
                    browser_ready=browser_ready,
                )
                append_debug_event(
                    "voice_stopped",
                    "Voice stop verification finished",
                    verified=verified,
                    stop_method=method,
                    elapsed_ms=total_elapsed_ms,
                    ui_active_after=ui_after,
                    browser_ready=browser_ready,
                )
                snapshot("after_voice_stop")
                if not browser_ready:
                    next_page_refresh = time.monotonic() + 0.5
                idle_state()
                LOG.info(
                    "ChatGPT Voice stop finished; verified=%s method=%s elapsed=%dms",
                    verified,
                    method,
                    total_elapsed_ms,
                )

            elif command.startswith("volume:"):
                try:
                    percent = min(150, max(0, int(command.split(":", 1)[1])))
                    assistant_volume_target = percent
                    cfg.assistant_volume_percent = percent
                    display = browser_display()
                    changed = set_assistant_volume(percent, x11_display=display)
                    volume_stream_present = changed > 0
                    next_volume_enforce = 0.0 if voice_active else time.monotonic() + 1.0
                    append_debug_event(
                        "assistant_volume",
                        f"{percent}%",
                        changed_streams=changed,
                        queued_until_stream=voice_active and changed == 0,
                        x11_display=display,
                        voice_active=voice_active,
                    )
                    LOG.info(
                        "Assistant volume target: %d%% changed=%d display=%s voice_active=%s",
                        percent,
                        changed,
                        display,
                        voice_active,
                    )
                except (TypeError, ValueError) as exc:
                    append_debug_event("assistant_volume_failed", command, error=str(exc))

            elif command in {"debug_snapshot", "browser_snapshot"}:
                snapshot("manual_debug_snapshot")

            elif command == "debug_snapshot_quiet":
                snapshot("live_debug_preview", log_success=False)

            elif command == "browser_reload":
                try:
                    if browser is None or not browser.is_running():
                        start_permanent_browser()
                    assert browser is not None
                    browser_ready = browser.reload_chat(timeout_ms=20_000)
                    append_debug_event("browser_reload", "manual reload", ready=browser_ready)
                    snapshot("after_browser_reload")
                    idle_state()
                except Exception as exc:
                    LOG.error("Could not reload hidden ChatGPT tab: %s", exc, exc_info=True)
                    append_debug_event("browser_reload_failed", str(exc))
                    browser_ready = False
                    next_page_refresh = time.monotonic() + 5.0
                    idle_state()

            elif command in {"browser_show", "browser_hide"}:
                _notify(
                    "EGL",
                    "Служебный Chromium работает на приватном виртуальном дисплее и всегда невидим.",
                )

            elif command in {"shutdown", "quit"}:
                stopping.set()

            if voice_active:
                indicator.send(level=meter.level, mode="listening")

                # Persistent volume guard: the stream may appear long after the
                # Voice UI opens, and Chromium may recreate it during a session.
                # Re-apply the target periodically, with faster polling while no
                # stream has been seen yet.
                if now >= next_volume_enforce:
                    display = browser_display()
                    changed = set_assistant_volume(
                        assistant_volume_target,
                        x11_display=display,
                    )
                    present = changed > 0
                    if present != volume_stream_present:
                        append_debug_event(
                            "assistant_volume_stream_found" if present else "assistant_volume_stream_waiting",
                            f"{assistant_volume_target}%",
                            changed_streams=changed,
                            x11_display=display,
                        )
                    volume_stream_present = present
                    next_volume_enforce = now + (1.25 if present else 0.35)

    finally:
        append_debug_event("daemon_stopping", "EGL daemon stopping")
        write_state("stopping")
        listener.set_voice_active(False)
        control.close()
        listener.close()
        meter.close()
        indicator.close()
        close_browser()
        write_state("offline")
    return 0
