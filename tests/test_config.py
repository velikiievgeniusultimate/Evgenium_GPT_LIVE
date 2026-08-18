import os
import tempfile
import unittest
from pathlib import Path


class ConfigTests(unittest.TestCase):
    def test_default_paths_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            old = {k: os.environ.get(k) for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR")}
            try:
                os.environ["XDG_CONFIG_HOME"] = str(Path(td) / "config")
                os.environ["XDG_DATA_HOME"] = str(Path(td) / "data")
                os.environ["XDG_STATE_HOME"] = str(Path(td) / "state")
                os.environ["XDG_RUNTIME_DIR"] = str(Path(td) / "run")
                import egl.config as c
                cfg = c.EGLConfig.default()
                cfg.chat_url = "https://chatgpt.com/c/test"
                c.save_config(cfg)
                loaded = c.load_config()
                self.assertEqual(loaded.chat_url, cfg.chat_url)
                self.assertEqual(loaded.wake_phrase, "евгениум слушай")
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
