import json
import os
import tempfile
import unittest
from pathlib import Path


class ConfigTests(unittest.TestCase):
    def test_default_paths_roundtrip_and_browser_policy_migration(self):
        with tempfile.TemporaryDirectory() as td:
            old_home = os.environ.get("EGL_HOME")
            old_runtime = os.environ.get("XDG_RUNTIME_DIR")
            try:
                egl_home = Path(td) / "Evgenium_GPT"
                os.environ["EGL_HOME"] = str(egl_home)
                os.environ["XDG_RUNTIME_DIR"] = str(Path(td) / "run")

                import egl.config as c

                cfg = c.EGLConfig.default()
                self.assertEqual(Path(cfg.browser_profile_path), egl_home / "data" / "browser-profile-system")
                self.assertTrue(Path(cfg.vosk_model_path).is_relative_to(egl_home))
                self.assertTrue(cfg.browser_headless)
                self.assertTrue(cfg.browser_keep_alive)
                self.assertEqual(cfg.wake_aliases, ["евгениум слушай"])
                self.assertEqual(cfg.stop_aliases, ["евгениум стоп"])
                self.assertAlmostEqual(cfg.wake_confidence_threshold, 0.86)
                self.assertAlmostEqual(cfg.stop_confidence_threshold, 0.35)

                cfg.chat_url = "https://chatgpt.com/c/test"
                cfg.microphone_device = 7
                path = c.save_config(cfg)
                self.assertEqual(path, egl_home / "config" / "config.json")

                loaded = c.load_config()
                self.assertEqual(loaded.chat_url, cfg.chat_url)
                self.assertEqual(loaded.wake_phrase, "евгениум слушай")
                self.assertEqual(loaded.microphone_device, 7)
                self.assertTrue(loaded.browser_headless)
                self.assertTrue(loaded.browser_keep_alive)

                # Simulate an old config with soft aliases and browser policy
                # choices. Current EGL must migrate all of them.
                raw = json.loads(path.read_text(encoding="utf-8"))
                raw["browser_headless"] = False
                raw["browser_keep_alive"] = False
                raw["wake_aliases"] = ["евгениум слушай", "евгений слушай", "евгениум слушает"]
                raw["stop_aliases"] = ["евгениум стоп", "евгений стоп"]
                path.write_text(json.dumps(raw), encoding="utf-8")
                migrated = c.load_config()
                self.assertTrue(migrated.browser_headless)
                self.assertTrue(migrated.browser_keep_alive)
                self.assertEqual(migrated.wake_aliases, ["евгениум слушай"])
                self.assertEqual(migrated.stop_aliases, ["евгениум стоп"])
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
