import unittest

from egl.microphone import input_device_label, resolve_input_sample_rate


class FakeSoundDevice:
    def __init__(self, default_rate=48000, accepted=(48000,)):
        self.default_rate = default_rate
        self.accepted = set(accepted)
        self.checked = []

    def query_devices(self, device, kind):
        self.assert_kind = kind
        return {
            "name": "Audient iD4",
            "max_input_channels": 2,
            "default_samplerate": self.default_rate,
        }

    def check_input_settings(self, *, device, channels, dtype, samplerate):
        self.checked.append(samplerate)
        if samplerate not in self.accepted:
            raise RuntimeError("Invalid sample rate")


class MicrophoneRateTests(unittest.TestCase):
    def test_prefers_native_default_rate(self):
        sd = FakeSoundDevice(default_rate=48000, accepted=(48000,))
        self.assertEqual(resolve_input_sample_rate(sd, 12), 48000)
        self.assertEqual(sd.checked, [48000])

    def test_falls_back_when_reported_default_is_not_openable(self):
        sd = FakeSoundDevice(default_rate=96000, accepted=(48000,))
        self.assertEqual(resolve_input_sample_rate(sd, 12), 48000)
        self.assertEqual(sd.checked[:2], [96000, 48000])

    def test_device_label_includes_native_rate(self):
        label = input_device_label(
            {"name": "Audient iD4", "default_samplerate": 48000.0},
            12,
        )
        self.assertEqual(label, "12: Audient iD4 — 48000 Hz")


if __name__ == "__main__":
    unittest.main()
