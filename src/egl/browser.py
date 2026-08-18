from __future__ import annotations

import logging
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

LOG = logging.getLogger(__name__)
CHATGPT_ORIGIN = "https://chatgpt.com"
NAVIGATION_TIMEOUT_MS = 15_000

VOICE_START_SELECTORS = [
    'button[data-testid="composer-speech-button"]',
    'button[data-testid="voice-mode-button"]',
    'button[aria-label*="voice" i]',
    'button[title*="voice" i]',
    'button[aria-label*="голос" i]',
    'button[title*="голос" i]',
]

VOICE_EXIT_SELECTORS = [
    'button[data-testid="voice-mode-close-button"]',
    'button[data-testid="voice-mode-exit-button"]',
    'button[aria-label*="exit" i]',
    'button[aria-label*="end" i]',
    'button[title*="exit" i]',
    'button[aria-label*="заверш" i]',
    'button[aria-label*="выйти" i]',
]

SYSTEM_BROWSER_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome-stable",
    "google-chrome",
    "brave-browser",
    "brave",
    "vivaldi-stable",
    "vivaldi",
)


class BrowserAutomationError(RuntimeError):
    pass


def find_system_browser() -> Path | None:
    """Find a normal Chromium-family browser installed by the user/OS."""
    override = os.environ.get("EGL_BROWSER", "").strip()
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return path
        resolved = shutil.which(override)
        return Path(resolved) if resolved else None

    for name in SYSTEM_BROWSER_CANDIDATES:
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved)
    return None


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ChatGPTBrowser:
    """Drive a dedicated normal Chromium-family browser through DevTools/CDP.

    First-time setup launches a visible browser without Playwright attached.
    Runtime uses the same persistent profile but launches it minimized. On KDE
    the optional EGL KWin script additionally removes the service window from
    the taskbar, pager and Alt+Tab.
    """

    def __init__(self, profile: Path, chat_url: str, headless: bool = True) -> None:
        self.profile = profile
        self.chat_url = chat_url
        self.background = headless
        self._pw = None
        self._browser = None
        self._browser_process: subprocess.Popen[bytes] | None = None
        self._debug_port: int | None = None
        self.context = None
        self.page = None

    def _endpoint(self) -> str:
        if self._debug_port is None:
            raise BrowserAutomationError("Browser DevTools port is not initialized")
        return f"http://127.0.0.1:{self._debug_port}"

    def is_running(self) -> bool:
        return bool(self._browser_process and self._browser_process.poll() is None)

    def launch_only(self) -> None:
        """Launch the normal browser and wait for DevTools, without automation."""
        if self.is_running():
            return

        executable = find_system_browser()
        if executable is None:
            raise BrowserAutomationError(
                "No normal Chromium-family browser was found. Install Chromium/Chrome "
                "or set EGL_BROWSER=/path/to/browser. On Arch: sudo pacman -S chromium"
            )

        self.profile.mkdir(parents=True, exist_ok=True)
        self._debug_port = _free_local_port()
        target = self.chat_url or CHATGPT_ORIGIN

        args = [
            str(executable),
            f"--user-data-dir={self.profile}",
            f"--remote-debugging-port={self._debug_port}",
            "--remote-debugging-address=127.0.0.1",
            "--no-first-run",
            "--no-default-browser-check",
            "--autoplay-policy=no-user-gesture-required",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
        ]
        if self.background:
            # Chromium officially supports --class on Linux. It gives KWin an
            # EGL-specific windowClass so no other Chromium windows are touched.
            args.extend(["--start-minimized", "--class=EvgeniumGPT"])
        args.append(target)

        LOG.info("Launching system browser for EGL: %s", executable)
        self._browser_process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        endpoint = self._endpoint()
        deadline = time.monotonic() + 20.0
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self._browser_process.poll() is not None:
                raise BrowserAutomationError(
                    f"System browser exited before DevTools became ready: {executable}"
                )
            try:
                with urllib.request.urlopen(f"{endpoint}/json/version", timeout=0.5) as response:
                    if response.status == 200:
                        return
            except Exception as exc:
                last_error = exc
                time.sleep(0.15)

        self.close()
        raise BrowserAutomationError(
            f"Could not connect to the system browser DevTools endpoint: {last_error}"
        )

    def attach(self) -> None:
        """Attach Playwright to an already-running normal browser via CDP."""
        from playwright.sync_api import sync_playwright

        if self._browser is not None:
            return
        if not self.is_running():
            raise BrowserAutomationError("System browser is not running")

        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.connect_over_cdp(self._endpoint())
            contexts = self._browser.contexts
            if not contexts:
                raise BrowserAutomationError("Connected browser did not expose a default context")
            self.context = contexts[0]

            try:
                self.context.grant_permissions(["microphone"], origin=CHATGPT_ORIGIN)
            except Exception:
                LOG.warning("Could not pre-grant microphone permission", exc_info=True)

            pages = self.context.pages
            self.page = pages[0] if pages else self.context.new_page()
            target = self.chat_url or CHATGPT_ORIGIN
            if not self.page.url.startswith(target):
                self.page.goto(target, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
            if self.background:
                self.hide_window()
        except BrowserAutomationError:
            raise
        except Exception as exc:
            raise BrowserAutomationError(f"Could not attach/open ChatGPT: {exc}") from exc

    def open(self) -> None:
        self.launch_only()
        self.attach()

    def _set_window_state(self, state: str) -> None:
        if self._browser is None or self.context is None or self.page is None:
            raise BrowserAutomationError("Browser is not attached")
        try:
            session = self.context.new_cdp_session(self.page)
            info = session.send("Browser.getWindowForTarget")
            session.send(
                "Browser.setWindowBounds",
                {"windowId": info["windowId"], "bounds": {"windowState": state}},
            )
            session.detach()
        except Exception as exc:
            raise BrowserAutomationError(f"Could not change browser window state: {exc}") from exc

    def show_window(self) -> None:
        self._set_window_state("normal")
        assert self.page is not None
        try:
            self.page.bring_to_front()
        except Exception:
            LOG.debug("Could not bring EGL browser to front", exc_info=True)

    def hide_window(self) -> None:
        self._set_window_state("minimized")

    def close(self) -> None:
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                LOG.debug("Could not close CDP browser cleanly", exc_info=True)
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                LOG.debug("Could not stop Playwright cleanly", exc_info=True)
        if self._browser_process and self._browser_process.poll() is None:
            try:
                self._browser_process.terminate()
                self._browser_process.wait(timeout=3)
            except Exception:
                try:
                    self._browser_process.kill()
                except Exception:
                    pass

        self.context = None
        self.page = None
        self._browser = None
        self._pw = None
        self._browser_process = None
        self._debug_port = None

    def __enter__(self) -> "ChatGPTBrowser":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    def _click_first(self, selectors: list[str], timeout_ms: int = 1000) -> bool:
        assert self.page is not None
        for selector in selectors:
            try:
                loc = self.page.locator(selector).first
                if loc.count() and loc.is_visible(timeout=timeout_ms):
                    loc.click(timeout=5_000)
                    return True
            except Exception:
                continue
        return False

    def has_voice_button(self) -> bool:
        assert self.page is not None
        for selector in VOICE_START_SELECTORS:
            try:
                loc = self.page.locator(selector).first
                if loc.count() and loc.is_visible(timeout=300):
                    return True
            except Exception:
                pass
        return False

    def start_voice(self) -> None:
        assert self.page is not None
        try:
            if self.chat_url and not self.page.url.startswith(self.chat_url):
                self.page.goto(
                    self.chat_url,
                    wait_until="domcontentloaded",
                    timeout=NAVIGATION_TIMEOUT_MS,
                )
            if not self._click_first(VOICE_START_SELECTORS, timeout_ms=1200):
                labels = self._button_labels()
                raise BrowserAutomationError(
                    "Voice button not found. ChatGPT may be unreachable or the web UI changed. "
                    f"Visible button labels: {labels[:20]}"
                )
            time.sleep(1.0)
        except BrowserAutomationError:
            raise
        except Exception as exc:
            raise BrowserAutomationError(f"Could not open ChatGPT Voice: {exc}") from exc

    def stop_voice(self) -> None:
        assert self.page is not None
        if self._click_first(VOICE_EXIT_SELECTORS, timeout_ms=500):
            time.sleep(0.4)
            return
        if self.chat_url:
            self.page.goto(
                self.chat_url,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT_MS,
            )
        else:
            self.page.goto(CHATGPT_ORIGIN, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)

    def _button_labels(self) -> list[str]:
        assert self.page is not None
        try:
            return self.page.locator("button").evaluate_all(
                "els => els.filter(e => !!(e.offsetWidth || e.offsetHeight)).map(e => e.getAttribute('aria-label') || e.getAttribute('title') || e.innerText || '').filter(Boolean)"
            )
        except Exception:
            return []

    @staticmethod
    def is_chat_url(url: str) -> bool:
        return bool(re.match(r"^https://chatgpt\.com/(?:c|g|project)/", url))
