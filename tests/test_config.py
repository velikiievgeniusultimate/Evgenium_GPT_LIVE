import os
import tempfile
import unittest
from pathlib import Path


class ConfigTests(unittest.TestCase):
    def test_default_paths_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            old_home = os.environ.get("EGL_HOME")
            old_runtime = os.environ.get("XDG_RUNTIME_DIR")
            try:
                egl_home = Path(td) / "Evgenium_GPT"
                os.environ["EGL_HOME"] = str(egl_home)
                os.environ["XDG_RUNTIME_DIR"] = str(Path(td) / "run")

                import egl.config as c

                cfg = c.EGLConfig.default()
                self.assertEqual(Path(cfg.browser_profile_path), egl_home / "data" / "browser-profile")
                self.assertTrue(Path(cfg.vosk_model_path).is_relative_to(egl_home))

                cfg.chat_url = "https://chatgpt.com/c/test"
                path = c.save_config(cfg)
                self.assertEqual(path, egl_home / "config" / "config.json")

                loaded = c.load_config()
                self.assertEqual(loaded.chat_url, cfg.chat_url)
                self.assertEqual(loaded.wake_phrase, "евгениум слушай")
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
