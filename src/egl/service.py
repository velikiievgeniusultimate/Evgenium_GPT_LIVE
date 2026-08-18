from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def unit_path() -> Path:
    return Path.home() / ".config/systemd/user/egl.service"


def install_service(enable: bool = True) -> Path:
    target = unit_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    executable = Path(sys.argv[0]).resolve()
    if executable.name.startswith("python"):
        candidate = Path(sys.executable).with_name("egl")
        if candidate.exists():
            executable = candidate

    unit = f"""[Unit]
Description=Evgenium GPT LIVE (EGL)
After=network-online.target pipewire.service pipewire-pulse.service
Wants=network-online.target

[Service]
Type=simple
ExecStart={executable} daemon
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""
    target.write_text(unit, encoding="utf-8")
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        if enable:
            subprocess.run(["systemctl", "--user", "enable", "--now", "egl.service"], check=False)
    return target


def uninstall_service() -> None:
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "disable", "--now", "egl.service"], check=False)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    try:
        unit_path().unlink()
    except FileNotFoundError:
        pass
