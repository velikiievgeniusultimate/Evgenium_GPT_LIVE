import tempfile
import unittest
from pathlib import Path

from egl.hotword import HotwordListener


class HotwordDebugTests(unittest.TestCase):
    def make_listener(self, *, on_wake, on_stop, debug=None):
        return HotwordListener(
            model_path=Path(tempfile.gettempdir()),
            wake_aliases=["евгениум слушай"],
            stop_aliases=["евгениум стоп"],
            on_wake=on_wake,
            on_stop=on_stop,
            on_debug=debug,
            wake_confidence_threshold=0.86,
            stop_confidence_threshold=0.35,
        )

    def test_partial_wake_is_rejected_even_with_high_confidence(self):
        events = []
        woke = []
        listener = self.make_listener(on_wake=lambda: woke.append(True), on_stop=lambda: None, debug=events.append)
        listener._dispatch("евгениум слушай", final=False, confidence=0.99)
        self.assertEqual(woke, [])
        self.assertEqual(events[-1]["reason"], "wake_partial_rejected")
        self.assertIsNone(events[-1]["accepted"])

    def test_low_confidence_final_wake_is_rejected(self):
        events = []
        woke = []
        listener = self.make_listener(on_wake=lambda: woke.append(True), on_stop=lambda: None, debug=events.append)
        listener._dispatch("евгениум слушай", final=True, confidence=0.71)
        self.assertEqual(woke, [])
        self.assertEqual(events[-1]["reason"], "wake_confidence_too_low")

    def test_strict_final_wake_is_accepted(self):
        events = []
        woke = []
        listener = self.make_listener(on_wake=lambda: woke.append(True), on_stop=lambda: None, debug=events.append)
        listener._dispatch("евгениум слушай", final=True, confidence=0.94)
        self.assertEqual(woke, [True])
        self.assertEqual(events[-1]["accepted"], "wake")
        self.assertEqual(events[-1]["reason"], "strict_final_wake")

    def test_soft_alias_does_not_wake(self):
        woke = []
        listener = self.make_listener(on_wake=lambda: woke.append(True), on_stop=lambda: None)
        listener._dispatch("евгений слушай", final=True, confidence=0.99)
        self.assertEqual(woke, [])

    def test_partial_stop_fires_immediately_while_voice_active(self):
        events = []
        stopped = []
        listener = self.make_listener(on_wake=lambda: None, on_stop=lambda: stopped.append(True), debug=events.append)
        listener.set_voice_active(True)
        listener._dispatch("евгениум стоп", final=False, confidence=0.60)
        self.assertEqual(stopped, [True])
        self.assertEqual(events[-1]["accepted"], "stop")
        self.assertEqual(events[-1]["reason"], "partial_fast_stop")

    def test_stop_is_not_suppressed_by_recent_wake(self):
        woke = []
        stopped = []
        listener = self.make_listener(on_wake=lambda: woke.append(True), on_stop=lambda: stopped.append(True))
        listener._dispatch("евгениум слушай", final=True, confidence=0.95)
        listener.set_voice_active(True)
        listener._dispatch("евгениум стоп", final=False, confidence=0.65)
        self.assertEqual(woke, [True])
        self.assertEqual(stopped, [True])

    def test_stop_fires_only_once_per_voice_session(self):
        stopped = []
        listener = self.make_listener(on_wake=lambda: None, on_stop=lambda: stopped.append(True))
        listener.set_voice_active(True)
        listener._dispatch("евгениум стоп", final=False, confidence=0.60)
        listener._dispatch("евгениум стоп", final=True, confidence=0.95)
        self.assertEqual(stopped, [True])


if __name__ == "__main__":
    unittest.main()
