import tempfile
import unittest
from pathlib import Path

from egl.browser import ChatGPTBrowser


class FakePage:
    def __init__(self):
        self.gotos = []

    def goto(self, url, **kwargs):
        self.gotos.append((url, kwargs))
        return None


class BrowserStopTests(unittest.TestCase):
    def make_browser(self):
        browser = ChatGPTBrowser(Path(tempfile.gettempdir()) / "egl-test-profile", "https://chatgpt.com/c/test")
        browser.page = FakePage()
        return browser

    def test_exit_click_is_fast_path(self):
        browser = self.make_browser()
        browser._click_first = lambda selectors, timeout_ms=0: True  # type: ignore[method-assign]
        browser._wait_voice_inactive = lambda timeout_s=0: True  # type: ignore[method-assign]
        self.assertTrue(browser.stop_voice())
        self.assertEqual(browser.last_stop_method, "exit_click")
        self.assertLess(browser.last_stop_elapsed_ms, 1000)

    def test_navigation_happens_immediately_when_exit_does_not_verify(self):
        browser = self.make_browser()
        calls = []
        browser._click_first = lambda selectors, timeout_ms=0: False  # type: ignore[method-assign]

        def inactive(timeout_s=0):
            calls.append(timeout_s)
            return True

        browser._wait_voice_inactive = inactive  # type: ignore[method-assign]
        self.assertTrue(browser.stop_voice())
        self.assertEqual(browser.last_stop_method, "forced_navigation")
        self.assertEqual(browser.page.gotos[0][0], "https://chatgpt.com/c/test")
        self.assertLessEqual(calls[-1], 0.25)


if __name__ == "__main__":
    unittest.main()
