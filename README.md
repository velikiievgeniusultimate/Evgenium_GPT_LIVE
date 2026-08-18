# Evgenium GPT LIVE — EGL

**EGL** turns the regular ChatGPT **web Voice** into a small Linux voice assistant without using the OpenAI API.

The intended interaction is simple:

- say **«Евгениум слушай»** → EGL opens Voice in one remembered ChatGPT chat;
- talk normally to ChatGPT;
- while Voice is active, a small live orb appears at the **bottom-left** of the desktop;
- the orb breathes while the session is live and reacts to desktop output volume when `parec` is available;
- say **«Евгениум стоп»** → EGL locally ends the Voice session;
- Chromium uses a dedicated persistent profile, so the ChatGPT login survives restarts.

> Status: early Linux MVP. Web UI automation is inherently sensitive to ChatGPT DOM changes; selectors are isolated in `src/egl/browser.py` so fixes stay small.

## Architecture

```text
microphone
    │
    ├─ Vosk (offline phrase detector)
    │      ├─ «Евгениум слушай» ─────┐
    │      └─ «Евгениум стоп» ───────┤
    │                                 ▼
    │                          EGL daemon
    │                           │       │
    │                           │       ├─ live desktop orb
    │                           │       │   └─ Pulse/PipeWire output RMS
    │                           │       │
    │                           ▼       │
    └──────────────────► Playwright Chromium
                          dedicated profile
                               │
                               ▼
                    remembered chatgpt.com chat
                               │
                          ChatGPT Voice
```

The wake/stop detector is local. Normal conversation is **not** transcribed by EGL — it is handled by ChatGPT Voice in the browser.

## Requirements

The first MVP targets a normal Linux desktop (Arch/KDE is the primary target).

- Python 3.11+
- PipeWire/PulseAudio-compatible desktop audio
- a working microphone
- `systemd --user`
- graphical session for the orb

Recommended on Arch:

```bash
sudo pacman -S --needed python pipewire pipewire-pulse pulseaudio-utils
```

`pulseaudio-utils` provides `pactl`/`parec`; EGL uses them only to make the orb react to output audio. Voice itself can still work without the meter.

## Install

```bash
git clone https://github.com/velikiievgeniusultimate/Evgenium_GPT_LIVE.git
cd Evgenium_GPT_LIVE
./install.sh
```

`install.sh` creates an isolated venv in `~/.local/share/egl/venv`, installs EGL and Playwright Chromium, then starts the setup wizard.

### First setup

EGL will:

1. download the small Russian Vosk model (~45 MB);
2. show available microphone devices;
3. open a **visible** dedicated Chromium profile;
4. ask you to sign in to ChatGPT once;
5. ask you to open the exact chat you want EGL to reuse;
6. remember that chat URL and browser profile;
7. install and start `egl.service` as a user service.

No ChatGPT password is stored by EGL. Browser cookies/local storage live in the dedicated Chromium profile at `~/.local/share/egl/browser-profile`.

After setup the runtime browser is headless by default.

## Usage

Say:

```text
Евгениум слушай
```

The orb appears and EGL clicks the ChatGPT Voice button in the remembered chat.

To finish:

```text
Евгениум стоп
```

The stop phrase is recognized **locally**, independently of ChatGPT. If the current ChatGPT UI no longer exposes a recognizable Exit button, EGL falls back to reloading the remembered chat, which tears down the active Voice view.

### Safety/manual commands

```bash
egl wake        # start Voice without saying the wake phrase
egl stop        # force-stop Voice
egl status      # idle / listening / error / offline
egl service restart
egl service logs
```

These are useful while tuning the hotword detector or after a ChatGPT UI change.

## Live orb

The orb is intentionally separate from Chromium. It appears only while EGL considers ChatGPT Voice active.

- yellow: Voice is starting;
- blue/cyan: Voice is active;
- red: browser automation failed;
- size pulsation: output audio level when `parec` can monitor the default sink;
- otherwise it uses a subtle breathing animation so there is always a visible “microphone is live” signal.

On KDE Wayland, if XWayland (`DISPLAY`) is available, the orb asks Qt to use X11/XWayland because tiny always-on-top overlays can then be positioned reliably in the lower-left corner. Native Wayland placement is compositor-dependent.

## About «Евгениум» recognition

The exact configured wake and stop phrases are:

```text
Евгениум слушай
Евгениум стоп
```

The first implementation uses Vosk with a tiny restricted Russian grammar. Because **«Евгениум» is an invented word**, Vosk may acoustically render it as a nearby known word such as «Евгений». EGL therefore includes a couple of recognition aliases while preserving the user-facing phrase.

If this is not reliable enough, the hotword module is deliberately isolated so it can later be replaced with a custom wake-word model without touching browser control or the UI orb.

## Files

```text
~/.config/egl/config.json                 EGL settings (0600)
~/.local/share/egl/browser-profile/       dedicated ChatGPT Chromium profile
~/.local/share/egl/models/                offline Vosk model
~/.local/share/egl/venv/                  install.sh virtual environment
~/.local/state/egl/state.json             current daemon state
~/.config/systemd/user/egl.service        autostart service
```

## Known limitations

1. **ChatGPT Web has no public API for “start Voice”.** EGL automates the normal Voice/Exit buttons with Playwright. A substantial ChatGPT UI change can require selector updates.
2. Runtime headless Chromium + microphone/audio needs real-world testing across Linux audio stacks. `egl wake` is provided specifically to test browser control separately from hotword recognition.
3. The orb's audio meter currently watches the **default desktop output**, not only ChatGPT's Chromium stream. Other audio playing at the same time can make it pulse.
4. Vosk small Russian is lightweight but not a purpose-trained wake-word engine. A custom model is a planned hardening step.
5. This project automates the user's own logged-in ChatGPT web session. It does not bypass plan limits, authentication or platform restrictions.

## Development

Fast checks that do not require audio/GUI/ChatGPT:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests
```

For a local editable install:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
python -m playwright install chromium
egl setup --no-service
```

## License

MIT.
