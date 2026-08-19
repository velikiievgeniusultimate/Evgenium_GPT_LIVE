import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import egl.service as service


class ServiceInstallTests(unittest.TestCase):
    def test_install_resets_failed_state_before_restart(self):
        calls: list[list[str]] = []

        class Result:
            returncode = 0

        def fake_run(args, **kwargs):
            calls.append(list(args))
            return Result()

        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "egl.service"
            with (
                patch.object(service, "unit_path", return_value=target),
                patch.object(service, "app_home", return_value=Path(td) / "home"),
                patch.object(service.shutil, "which", return_value="/usr/bin/systemctl"),
                patch.object(service.subprocess, "run", side_effect=fake_run),
            ):
                service.install_service(enable=True)

        self.assertEqual(
            calls,
            [
                ["systemctl", "--user", "daemon-reload"],
                ["systemctl", "--user", "enable", "egl.service"],
                ["systemctl", "--user", "reset-failed", "egl.service"],
                ["systemctl", "--user", "restart", "egl.service"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
