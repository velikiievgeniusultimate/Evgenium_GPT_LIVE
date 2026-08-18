import tempfile
import unittest
from pathlib import Path

from egl.hotword import HotwordListener


class HotwordDebugTests(unittest.TestCase):
    def test_stop_match_is_reported_while_voice_active(self):
        debug = []
        stopped = []
        listener = HotwordListener(
            model_path=Path(tempfile.gettempdir()),
            wake_aliases=["евгениум слушай"],
            stop_aliases=["евгениум стоп"],
            on_wake=lambda: None,
            on_stop=lambda: stopped.append(True),
            on_debug=lambda text, active, wake, stop: debug.append((text, active, wake, stop)),
        )
        listener.set_voice_active(True)
        listener._dispatch("евгениум стоп")
        self.assertEqual(debug[-1], ("евгениум стоп", True, False, True))
        self.assertEqual(stopped, [True])

    def test_wake_match_is_reported_while_idle(self):
        debug = []
        woke = []
        listener = HotwordListener(
            model_path=Path(tempfile.gettempdir()),
            wake_aliases=["евгениум слушай"],
            stop_aliases=["евгениум стоп"],
            on_wake=lambda: woke.append(True),
            on_stop=lambda: None,
            on_debug=lambda text, active, wake, stop: debug.append((text, active, wake, stop)),
        )
        listener._dispatch("евгениум слушай")
        self.assertEqual(debug[-1], ("евгениум слушай", False, True, False))
        self.assertEqual(woke, [True])


if __name__ == "__main__":
    unittest.main()
