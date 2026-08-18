import os
import tempfile
import unittest
from pathlib import Path


class DebugStateTests(unittest.TestCase):
    def test_debug_event_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            old_home = os.environ.get("EGL_HOME")
            old_runtime = os.environ.get("XDG_RUNTIME_DIR")
            try:
                os.environ["EGL_HOME"] = str(Path(td) / "Evgenium_GPT")
                os.environ["XDG_RUNTIME_DIR"] = str(Path(td) / "run")

                from egl.state import append_debug_event, debug_screenshot_path, read_debug_events

                append_debug_event(
                    "voice_stopped",
                    "verified stop",
                    verified=True,
                    ui_active_after=False,
                )
                events = read_debug_events()
                self.assertEqual(events[-1]["event"], "voice_stopped")
                self.assertTrue(events[-1]["verified"])
                self.assertFalse(events[-1]["ui_active_after"])
                self.assertTrue(debug_screenshot_path().is_relative_to(Path(os.environ["EGL_HOME"])))
            finally:
                if old_home is None:
                    os.environ.pop("EGL_HOME", None)
                else:
                    os.environ["EGL_HOME"] = old_home
                if old_runtime is None:
                    os.environ.pop("XDG_RUNTIME_DIR", None)
                else:
                    os.environ["XDG_RUNTIME_DIR"] = old_runtime


if __name__ == "__main__":
    unittest.main()
