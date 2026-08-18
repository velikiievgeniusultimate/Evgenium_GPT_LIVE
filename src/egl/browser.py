from __future__ import annotations

import logging
import re
import time
from pathlib import Path

LOG = logging.getLogger(__name__)
CHATGPT_ORIGIN = "https://chatgpt.com"

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


class BrowserAutomationError(RuntimeError):
    pass


class ChatGPTBrowser:
    def __init__(self, profile: Path, chat_url: str, headless: bool = True) -> None:
        self.profile = profile
        self.chat_url = chat_url
        self.headless = headless
        self._pw = None
        self.context = None
        self.page = None

    def open(self) -> None:
        from playwright.sync_api import sync_playwright

        self.profile.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self.context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile),
            headless=self.headless,
            channel="chromium",
            ignore_default_args=["--mute-audio"],
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
            ],
            no_viewport=True,
        )
        try:
            self.context.grant_permissions(["microphone"], origin=CHATGPT_ORIGIN)
        except Exception:
            LOG.warning("Could not pre-grant microphone permission", exc_info=True)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        if self.chat_url:
            self.page.goto(self.chat_url, wait_until="domcontentloaded", timeout=60_000)
        else:
            self.page.goto(CHATGPT_ORIGIN, wait_until="domcontentloaded", timeout=60_000)

    def close(self) -> None:
        if self.context:
            self.context.close()
        if self._pw:
            self._pw.stop()
        self.context = None
        self.page = None
        self._pw = None

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
        if self.chat_url and not self.page.url.startswith(self.chat_url):
            self.page.goto(self.chat_url, wait_until="domcontentloaded", timeout=60_000)
        if not self._click_first(VOICE_START_SELECTORS, timeout_ms=900):
            labels = self._button_labels()
            raise BrowserAutomationError(
                "Voice button not found. ChatGPT web UI may have changed. "
                f"Visible button labels: {labels[:20]}"
            )
        time.sleep(1.0)

    def stop_voice(self) -> None:
        assert self.page is not None
        if self._click_first(VOICE_EXIT_SELECTORS, timeout_ms=500):
            time.sleep(0.4)
            return
        # Hard fallback: navigation tears down the active WebRTC voice view.
        if self.chat_url:
            self.page.goto(self.chat_url, wait_until="domcontentloaded", timeout=60_000)
        else:
            self.page.goto(CHATGPT_ORIGIN, wait_until="domcontentloaded", timeout=60_000)

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
