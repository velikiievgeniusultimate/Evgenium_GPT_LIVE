from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .config import app_home


def unit_path() -> Path:
    return Path.home() / ".config/systemd/user/egl.service"


def _systemd_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def install_service(enable: bool = True) -> Path:
    target = unit_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    executable = Path(sys.argv[0]).resolve()
    if executable.name.startswith("python"):
        candidate = Path(sys.executable).with_name("egl")
        if candidate.exists():
            executable = candidate

    egl_home = app_home().resolve()
    executable_text = _systemd_quote(str(executable))
    home_text = _systemd_quote(str(egl_home))

    # Network is intentionally NOT an ordering dependency. EGL starts its
    # private Xvfb + Chromium immediately, but that local browser stack is able
    # to stay alive with VPN/network unavailable and recover the same tab later.
    # Start limiting still protects against genuine code/config crash loops.
    unit = f"""[Unit]
Description=Evgenium GPT LIVE (EGL)
After=pipewire.service pipewire-pulse.service
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
ExecStart=\"{executable_text}\" daemon
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=\"EGL_HOME={home_text}\"

[Install]
WantedBy=default.target
"""
    target.write_text(unit, encoding="utf-8")
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        if enable:
            # A previous bad build may have exhausted StartLimitBurst. Updating
            # the code does not clear that state automatically, so always reset
            # it before starting the freshly installed service.
            subprocess.run(["systemctl", "--user", "enable", "egl.service"], check=False)
            subprocess.run(["systemctl", "--user", "reset-failed", "egl.service"], check=False)
            subprocess.run(["systemctl", "--user", "restart", "egl.service"], check=False)
    return target


def uninstall_service() -> None:
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "disable", "--now", "egl.service"], check=False)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    try:
        unit_path().unlink()
    except FileNotFoundError:
        pass
