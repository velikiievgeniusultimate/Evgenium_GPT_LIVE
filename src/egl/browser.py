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


def find_xvfb() -> Path | None:
    resolved = shutil.which("Xvfb")
    return Path(resolved) if resolved else None


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _free_x_display() -> str:
    for number in range(90, 160):
        socket_path = Path(f"/tmp/.X11-unix/X{number}")
        lock_path = Path(f"/tmp/.X{number}-lock")
        if not socket_path.exists() and not lock_path.exists():
            return f":{number}"
    raise BrowserAutomationError("Could not find a free X display for EGL's hidden browser")


class ChatGPTBrowser:
    """Drive EGL's dedicated Chromium profile through DevTools/CDP.

    Setup uses a normal visible system browser so the user can authenticate.
    Runtime can use a private Xvfb display. In that mode Chromium is still a
    real headed browser (important for WebRTC/audio), but its window literally
    does not belong to the user's Plasma/Wayland desktop and cannot flash into
    the taskbar, Alt+Tab or overview.
    """

    def __init__(
        self,
        profile: Path,
        chat_url: str,
        headless: bool = True,
        *,
        virtual_display: bool = False,
    ) -> None:
        self.profile = profile
        self.chat_url = chat_url
        self.background = headless
        self.virtual_display = virtual_display
        self._pw = None
        self._browser = None
        self._browser_process: subprocess.Popen[bytes] | None = None
        self._xvfb_process: subprocess.Popen[bytes] | None = None
        self._debug_port: int | None = None
        self._display: str | None = None
        self.context = None
        self.page = None

    def _endpoint(self) -> str:
        if self._debug_port is None:
            raise BrowserAutomationError("Browser DevTools port is not initialized")
        return f"http://127.0.0.1:{self._debug_port}"

    def is_running(self) -> bool:
        browser_ok = bool(self._browser_process and self._browser_process.poll() is None)
        if not self.virtual_display:
            return browser_ok
        xvfb_ok = bool(self._xvfb_process and self._xvfb_process.poll() is None)
        return browser_ok and xvfb_ok

    def _start_virtual_display(self) -> None:
        if not self.virtual_display:
            return
        if self._xvfb_process and self._xvfb_process.poll() is None:
            return

        xvfb = find_xvfb()
        if xvfb is None:
            raise BrowserAutomationError(
                "Xvfb is required for the fully invisible runtime browser. "
                "On Arch install xorg-server-xvfb."
            )

        self._display = _free_x_display()
        self._xvfb_process = subprocess.Popen(
            [
                str(xvfb),
                self._display,
                "-screen",
                "0",
                "1280x720x24",
                "-nolisten",
                "tcp",
                "-noreset",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        number = self._display.removeprefix(":")
        socket_path = Path(f"/tmp/.X11-unix/X{number}")
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if self._xvfb_process.poll() is not None:
                raise BrowserAutomationError("EGL Xvfb exited during startup")
            if socket_path.exists():
                return
            time.sleep(0.05)
        raise BrowserAutomationError("EGL Xvfb did not become ready in time")

    def launch_only(self) -> None:
        """Launch Chromium and wait for DevTools, without attaching Playwright."""
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
        env = os.environ.copy()

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
            "--class=EvgeniumGPT",
        ]

        if self.virtual_display:
            self._start_virtual_display()
            assert self._display is not None
            env["DISPLAY"] = self._display
            env.pop("WAYLAND_DISPLAY", None)
            args.append("--ozone-platform=x11")
        elif self.background:
            # Visible-desktop fallback only. Normal runtime should use Xvfb.
            args.append("--start-minimized")

        args.append(target)

        LOG.info(
            "Launching EGL Chromium: %s (virtual display=%s, display=%s)",
            executable,
            self.virtual_display,
            self._display,
        )
        self._browser_process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
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

    def attach(self, *, navigate: bool = True, tolerate_navigation_failure: bool = False) -> None:
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
            if navigate:
                target = self.chat_url or CHATGPT_ORIGIN
                if not self.page.url.startswith(target):
                    try:
                        self.page.goto(target, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
                    except Exception:
                        if not tolerate_navigation_failure:
                            raise
                        LOG.info("Initial ChatGPT navigation is not ready yet", exc_info=True)
        except BrowserAutomationError:
            raise
        except Exception as exc:
            raise BrowserAutomationError(f"Could not attach/open ChatGPT: {exc}") from exc

    def open(self) -> None:
        self.launch_only()
        self.attach()

    def open_runtime(self) -> bool:
        """Start the permanent hidden runtime browser even if VPN/network is down.

        Browser/Xvfb/CDP startup is local and must succeed independently of
        ChatGPT. The return value only tells the daemon whether the Voice button
        is already ready.
        """
        self.launch_only()
        self.attach(navigate=True, tolerate_navigation_failure=True)
        return self.ensure_chat_ready(timeout_ms=4_000, reload=False)

    def ensure_chat_ready(self, *, timeout_ms: int = 8_000, reload: bool = False) -> bool:
        """Keep the remembered chat loaded and wait until its Voice button exists."""
        if self.page is None:
            return False

        if self.chat_url:
            should_navigate = reload or not self.page.url.startswith(self.chat_url)
            if should_navigate:
                try:
                    self.page.goto(
                        self.chat_url,
                        wait_until="domcontentloaded",
                        timeout=min(timeout_ms, NAVIGATION_TIMEOUT_MS),
                    )
                except Exception:
                    LOG.debug("ChatGPT page is not reachable/loaded yet", exc_info=True)
                    return False

        deadline = time.monotonic() + max(timeout_ms, 0) / 1000.0
        while time.monotonic() <= deadline:
            if self.has_voice_button():
                return True
            time.sleep(0.2)
        return False

    def reload_chat(self, *, timeout_ms: int = 15_000) -> bool:
        return self.ensure_chat_ready(timeout_ms=timeout_ms, reload=True)

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
        if self._xvfb_process and self._xvfb_process.poll() is None:
            try:
                self._xvfb_process.terminate()
                self._xvfb_process.wait(timeout=2)
            except Exception:
                try:
                    self._xvfb_process.kill()
                except Exception:
                    pass

        self.context = None
        self.page = None
        self._browser = None
        self._pw = None
        self._browser_process = None
        self._xvfb_process = None
        self._debug_port = None
        self._display = None

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
        if self.page is None:
            return False
        for selector in VOICE_START_SELECTORS:
            try:
                loc = self.page.locator(selector).first
                if loc.count() and loc.is_visible(timeout=250):
                    return True
            except Exception:
                pass
        return False

    def start_voice(self) -> None:
        if self.page is None:
            raise BrowserAutomationError("ChatGPT page is not attached")

        # Normally this is immediate because the daemon preloads the page. Keep
        # a generous readiness wait so a background refresh can never race the
        # wake phrase again.
        if not self.ensure_chat_ready(timeout_ms=5_000, reload=False):
            if not self.ensure_chat_ready(timeout_ms=15_000, reload=True):
                labels = self._button_labels()
                raise BrowserAutomationError(
                    "ChatGPT tab is open but Voice is not ready. Check VPN/network/login. "
                    f"Visible button labels: {labels[:20]}"
                )

        if not self._click_first(VOICE_START_SELECTORS, timeout_ms=2_000):
            raise BrowserAutomationError("Voice button disappeared before EGL could click it")
        time.sleep(0.8)

    def stop_voice(self) -> None:
        if self.page is None:
            return
        if self._click_first(VOICE_EXIT_SELECTORS, timeout_ms=700):
            time.sleep(0.4)
            return

        # Keep the permanent tab alive even if the Exit selector changes.
        if self.chat_url:
            try:
                self.page.goto(
                    self.chat_url,
                    wait_until="domcontentloaded",
                    timeout=NAVIGATION_TIMEOUT_MS,
                )
            except Exception:
                LOG.warning("Could not restore remembered chat after Voice stop", exc_info=True)

    def _button_labels(self) -> list[str]:
        if self.page is None:
            return []
        try:
            return self.page.locator("button").evaluate_all(
                "els => els.filter(e => !!(e.offsetWidth || e.offsetHeight)).map(e => e.getAttribute('aria-label') || e.getAttribute('title') || e.innerText || '').filter(Boolean)"
            )
        except Exception:
            return []

    @staticmethod
    def is_chat_url(url: str) -> bool:
        return bool(re.match(r"^https://chatgpt\.com/(?:c|g|project)/", url))
