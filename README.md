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

## One-line install

For the current MVP branch:

```bash
curl -fsSL https://raw.githubusercontent.com/velikiievgeniusultimate/Evgenium_GPT_LIVE/refs/heads/agent/egl-linux-mvp/bootstrap.sh | bash
```

The bootstrapper is intentionally interactive only where interaction is actually required. It will:

1. install/check Linux prerequisites (Arch/pacman, Debian/apt and Fedora/dnf are recognized; `sudo` may ask for your password);
2. clone/update the project into **`~/Evgenium_GPT`**;
3. create `~/Evgenium_GPT/.venv`;
4. install EGL and Playwright Chromium;
5. download/configure the local Russian Vosk model during setup;
6. open a visible dedicated Chromium profile once so you can sign in to ChatGPT;
7. ask you to open the exact chat EGL should remember;
8. save the selected chat and persistent browser profile;
9. install and start the `systemd --user` service.

No ChatGPT password is stored by EGL. The login remains inside EGL's dedicated Chromium profile.

### Main EGL directory

Almost everything belongs to one predictable place:

```text
~/Evgenium_GPT/
├── .git/                       project checkout
├── .venv/                      private Python environment
├── config/
│   └── config.json             EGL settings (0600)
├── data/
│   ├── browser-profile/        persistent ChatGPT login/session
│   └── models/                 local Vosk speech model
├── state/                      daemon state/fallback runtime data
├── src/                        EGL source code
├── bootstrap.sh
└── install.sh
```

Only two small integration files intentionally live outside that directory:

```text
~/.config/systemd/user/egl.service    autostart service
~/.local/bin/egl                      symlink to EGL CLI
```

Temporary IPC may use `$XDG_RUNTIME_DIR/egl`, which disappears with the user session.

You can override the installation directory if needed:

```bash
curl -fsSL https://raw.githubusercontent.com/velikiievgeniusultimate/Evgenium_GPT_LIVE/refs/heads/agent/egl-linux-mvp/bootstrap.sh | EGL_HOME="$HOME/My_EGL" bash
```

To skip automatic OS package installation:

```bash
curl -fsSL https://raw.githubusercontent.com/velikiievgeniusultimate/Evgenium_GPT_LIVE/refs/heads/agent/egl-linux-mvp/bootstrap.sh | EGL_SKIP_SYSTEM_DEPS=1 bash
```

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

The one-line bootstrapper attempts to install the basic system dependencies automatically. On Arch it uses packages such as `python`, `portaudio` and `pulseaudio-utils`.

`pulseaudio-utils` provides `pactl`/`parec`; EGL uses them only to make the orb react to output audio. Voice itself can still work without the meter.

## First setup

EGL will show available microphone devices and then open a **visible** dedicated Chromium profile.

1. Sign in to ChatGPT.
2. Open the chat you want EGL to reuse for voice sessions.
3. Return to the terminal and press ENTER.
4. EGL remembers the exact chat URL and browser profile.
5. The user service starts automatically.

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

If `~/.local/bin` is not currently in your shell PATH, the service still works; add that directory to PATH only for convenient manual `egl` commands.

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

## Updating

Running the same one-line installer again updates an existing clean `~/Evgenium_GPT` checkout and reinstalls the Python package. It refuses to overwrite local uncommitted Git changes.

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
