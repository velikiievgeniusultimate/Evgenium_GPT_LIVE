import unittest
from unittest.mock import patch

import egl.volume as volume


class VolumeTests(unittest.TestCase):
    def test_gui_autodiscovery_changes_only_private_egl_chromium(self):
        streams = [
            {
                "index": 17,
                "properties": {
                    "application.name": "WEBRTC VoiceEngine",
                    "application.process.binary": "Discord",
                    "media.role": "phone",
                    "window.x11.display": ":1",
                },
            },
            {
                "index": 18,
                "properties": {
                    "application.name": "Chromium",
                    "application.process.binary": "chromium",
                    "media.role": "phone",
                    "window.x11.display": ":90",
                },
            },
            {
                "index": 19,
                "properties": {
                    "application.name": "Chromium",
                    "application.process.binary": "chromium",
                    "media.role": "phone",
                    "window.x11.display": ":1",
                },
            },
        ]
        calls = []

        class Result:
            returncode = 0

        def fake_run(args, **kwargs):
            calls.append(args)
            return Result()

        with (
            patch.object(volume, "_pactl", return_value="/usr/bin/pactl"),
            patch.object(volume, "_sink_inputs", return_value=streams),
            patch.object(volume.subprocess, "run", side_effect=fake_run),
        ):
            changed = volume.set_assistant_volume(999)

        self.assertEqual(changed, 1)
        self.assertEqual(
            calls,
            [["/usr/bin/pactl", "set-sink-input-volume", "18", "150%"]],
        )

    def test_daemon_exact_display_targets_only_that_display(self):
        streams = [
            {
                "index": 21,
                "properties": {
                    "application.process.binary": "chromium",
                    "media.role": "phone",
                    "window.x11.display": ":90",
                },
            },
            {
                "index": 22,
                "properties": {
                    "application.process.binary": "chromium",
                    "media.role": "phone",
                    "window.x11.display": ":91",
                },
            },
        ]
        calls = []

        class Result:
            returncode = 0

        def fake_run(args, **kwargs):
            calls.append(args)
            return Result()

        with (
            patch.object(volume, "_pactl", return_value="/usr/bin/pactl"),
            patch.object(volume, "_sink_inputs", return_value=streams),
            patch.object(volume.subprocess, "run", side_effect=fake_run),
        ):
            changed = volume.set_assistant_volume(120, x11_display=":91")

        self.assertEqual(changed, 1)
        self.assertEqual(
            calls,
            [["/usr/bin/pactl", "set-sink-input-volume", "22", "120%"]],
        )

    def test_no_pactl_is_non_blocking(self):
        with patch.object(volume, "_pactl", return_value=None):
            self.assertEqual(volume.set_assistant_volume(120), 0)


if __name__ == "__main__":
    unittest.main()
