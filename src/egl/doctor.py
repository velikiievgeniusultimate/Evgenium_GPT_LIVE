from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

from .browser import find_system_browser
from .config import app_home, config_path, load_config


def _line(kind: str, text: str) -> None:
    print(f"[{kind:4}] {text}")


def run_doctor() -> int:
    """Check the pieces EGL needs without requiring a configured ChatGPT chat."""
    failures = 0

    print("\nEGL doctor")
    _line("INFO", f"Python: {sys.version.split()[0]} ({sys.executable})")
    _line("INFO", f"EGL_HOME: {app_home()}")

    for module in ("playwright", "vosk", "sounddevice", "PySide6"):
        try:
            importlib.import_module(module)
            _line("OK", f"Python module: {module}")
        except Exception as exc:
            failures += 1
            _line("FAIL", f"Python module {module}: {exc}")

    browser = find_system_browser()
    if browser:
        _line("OK", f"System Chromium-family browser: {browser}")
    else:
        failures += 1
        _line(
            "FAIL",
            "No system Chromium-family browser found. On Arch install chromium, "
            "or set EGL_BROWSER=/path/to/browser",
        )

    try:
        import sounddevice as sd

        devices = sd.query_devices()
        inputs = [d for d in devices if int(d.get("max_input_channels", 0)) > 0]
        if inputs:
            _line("OK", f"Microphone-capable audio devices: {len(inputs)}")
        else:
            _line("WARN", "No microphone-capable PortAudio devices reported")
    except Exception as exc:
        _line("WARN", f"Could not query microphone devices: {exc}")

    if shutil.which("pactl") and shutil.which("parec"):
        _line("OK", "pactl/parec available for the audio-reactive orb")
    else:
        _line("WARN", "pactl/parec missing; Voice can still work, orb will use breathing animation")

    if shutil.which("systemctl"):
        try:
            proc = subprocess.run(
                ["systemctl", "--user", "is-system-running"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
            state = proc.stdout.strip() or f"exit {proc.returncode}"
            _line("OK" if proc.returncode == 0 else "WARN", f"systemd --user: {state}")
        except Exception as exc:
            _line("WARN", f"systemd --user check failed: {exc}")
    else:
        _line("WARN", "systemctl not found; autostart service cannot be installed")

    if config_path().exists():
        try:
            cfg = load_config()
            _line("OK", f"Config: {config_path()}")
            if cfg.chat_url:
                _line("OK", f"Remembered ChatGPT chat: {cfg.chat_url}")
            else:
                _line("WARN", "Config exists but no ChatGPT chat is selected")
            model = Path(cfg.vosk_model_path)
            if model.exists() and (model / "conf").exists():
                _line("OK", f"Vosk model: {model}")
            else:
                _line("WARN", "Vosk model is not downloaded yet; setup will download it")
        except Exception as exc:
            failures += 1
            _line("FAIL", f"Config could not be read: {exc}")
    else:
        _line("WARN", "First-time setup has not created config.json yet")

    if failures:
        _line("FAIL", f"Doctor found {failures} blocking problem(s)")
        return 1
    _line("OK", "No blocking installation problems found")
    return 0
