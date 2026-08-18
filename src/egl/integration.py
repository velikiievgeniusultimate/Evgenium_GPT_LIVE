from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import app_home

KWIN_SCRIPT_ID = "eglwindowguard"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def desktop_entry_path() -> Path:
    return Path.home() / ".local/share/applications/egl-settings.desktop"


def kwin_script_target() -> Path:
    return Path.home() / ".local/share/kwin/scripts" / KWIN_SCRIPT_ID


def _egl_executable() -> Path:
    candidate = Path(sys.executable).with_name("egl")
    if candidate.exists():
        return candidate.resolve()
    return Path(sys.argv[0]).resolve()


def install_desktop_entry() -> Path:
    target = desktop_entry_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    executable = _egl_executable()
    content = f"""[Desktop Entry]
Type=Application
Name=Evgenium GPT LIVE
Comment=Configure EGL voice assistant
Exec={executable} gui
Icon=audio-input-microphone
Terminal=false
Categories=Utility;Settings;AudioVideo;
StartupNotify=true
StartupWMClass=EGLSettings
"""
    target.write_text(content, encoding="utf-8")

    sycoca = shutil.which("kbuildsycoca6") or shutil.which("kbuildsycoca5")
    if sycoca:
        subprocess.run(
            [sycoca],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return target


def is_plasma_session() -> bool:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    session = os.environ.get("DESKTOP_SESSION", "").lower()
    return "kde" in desktop or "plasma" in desktop or "plasma" in session


def install_kwin_script() -> Path | None:
    if not is_plasma_session() and not shutil.which("kwriteconfig6"):
        return None

    source = repo_root() / "kde/kwin/eglwindowguard"
    if not source.exists():
        return None

    target = kwin_script_target()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)

    kwrite = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
    if kwrite:
        subprocess.run(
            [
                kwrite,
                "--file",
                "kwinrc",
                "--group",
                "Plugins",
                "--key",
                f"{KWIN_SCRIPT_ID}Enabled",
                "true",
            ],
            check=False,
        )

    qdbus = shutil.which("qdbus6") or shutil.which("qdbus")
    if qdbus:
        subprocess.run(
            [qdbus, "org.kde.KWin", "/KWin", "reconfigure"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return target


def install_integrations() -> list[Path]:
    installed = [install_desktop_entry()]
    kwin = install_kwin_script()
    if kwin is not None:
        installed.append(kwin)
    return installed


def integration_summary() -> dict[str, object]:
    return {
        "egl_home": str(app_home()),
        "desktop_entry": desktop_entry_path().exists(),
        "plasma": is_plasma_session(),
        "kwin_script": kwin_script_target().exists(),
    }
