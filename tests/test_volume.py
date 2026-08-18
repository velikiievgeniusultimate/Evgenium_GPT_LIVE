import unittest
from unittest.mock import patch

import egl.volume as volume


class VolumeTests(unittest.TestCase):
    def test_only_egl_stream_is_changed_and_volume_is_clamped(self):
        streams = [
            {
                "index": 17,
                "properties": {"application.name": volume.EGL_AUDIO_APP_NAME},
            },
            {
                "index": 18,
                "properties": {"application.name": "Chromium"},
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
            [["/usr/bin/pactl", "set-sink-input-volume", "17", "150%"]],
        )

    def test_no_pactl_is_non_blocking(self):
        with patch.object(volume, "_pactl", return_value=None):
            self.assertEqual(volume.set_assistant_volume(120), 0)


if __name__ == "__main__":
    unittest.main()
