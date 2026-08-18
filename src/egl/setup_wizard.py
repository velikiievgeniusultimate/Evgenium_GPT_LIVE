from __future__ import annotations

import shutil
from pathlib import Path

from .browser import ChatGPTBrowser
from .config import ensure_dirs, load_config, save_config
from .model import ensure_vosk_model
from .service import install_service


def list_microphones() -> None:
    try:
        import sounddevice as sd
        print("\nAudio devices:")
        print(sd.query_devices())
    except Exception as exc:
        print(f"Could not enumerate audio devices: {exc}")


def run_setup(install_autostart: bool = True) -> int:
    # load_config() returns defaults when config.json does not exist and preserves
    # an existing configuration when setup is intentionally re-run.
    cfg = load_config()
    ensure_dirs()
    print("\nEGL — Evgenium GPT LIVE setup")
    print("Wake phrase : Евгениум слушай")
    print("Stop phrase : Евгениум стоп")

    if shutil.which("pactl") is None or shutil.which("parec") is None:
        print("\nNOTE: pactl/parec not found. The orb will still breathe, but cannot react to GPT output volume.")
        print("On Arch Linux they are provided by libpulse and work with pipewire-pulse/PulseAudio compatibility.")

    list_microphones()
    current = "default" if cfg.microphone_device is None else str(cfg.microphone_device)
    raw_device = input(f"\nMicrophone device index [{current}]: ").strip()
    if raw_device:
        try:
            cfg.microphone_device = int(raw_device)
        except ValueError:
            print("Invalid index; keeping the current microphone selection.")

    ensure_vosk_model(cfg.vosk_model_url, Path(cfg.vosk_model_path))

    print("\nOpening a dedicated Chromium profile for ChatGPT.")
    print("1. Sign in to ChatGPT if needed.")
    print("2. Open the chat that EGL should always use.")
    print("3. Return here and press ENTER.")

    browser = ChatGPTBrowser(Path(cfg.browser_profile_path), "", headless=False)
    browser.open()
    try:
        input("\nPress ENTER after the desired chat is open... ")
        assert browser.page is not None
        url = browser.page.url
        if not ChatGPTBrowser.is_chat_url(url):
            print(f"Current page does not look like a ChatGPT conversation: {url}")
            print("Open a concrete chat (/c/..., /g/... or /project/...) and run setup again.")
            return 2
        cfg.chat_url = url
        if browser.has_voice_button():
            print("✓ Voice button detected in the selected chat.")
        else:
            print("! Voice button was not detected. Setup will continue; selectors may need an update for your UI.")
        save_config(cfg)
    finally:
        browser.close()

    if install_autostart:
        path = install_service(enable=True)
        print(f"✓ systemd user service installed: {path}")
    print("\n✓ EGL configured.")
    print('Say: "Евгениум слушай"')
    print('Stop with: "Евгениум стоп"')
    print("Manual safety controls: egl wake / egl stop")
    print("Diagnostics: egl doctor")
    return 0
