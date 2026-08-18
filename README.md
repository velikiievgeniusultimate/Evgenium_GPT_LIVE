# Evgenium GPT LIVE — EGL

**EGL** is a Linux helper around the regular ChatGPT **Web Voice** session. It keeps the ChatGPT intelligence in the normal web product and adds Linux-native wake/stop phrases, a persistent browser profile, autostart and a live desktop orb.

Current version: **0.2.0** (early MVP, Arch/KDE is the primary target).

## What it should feel like

- say **«Евгениум слушай»** → EGL starts Voice in one remembered ChatGPT chat;
- talk normally to ChatGPT;
- while Voice is active, a live orb appears in the bottom-left corner;
- say **«Евгениум стоп»** → EGL locally terminates the Voice session;
- the dedicated Chromium profile keeps the ChatGPT login between restarts.

## One-line install

Use a cache-busting query so repeated installs always fetch the current `main` bootstrap rather than a recently cached raw GitHub response:

```bash
curl -fsSL "https://raw.githubusercontent.com/velikiievgeniusultimate/Evgenium_GPT_LIVE/refs/heads/main/bootstrap.sh?$(date +%s)" | bash
```

You should see this near the top:

```text
[EGL] Evgenium GPT LIVE bootstrap v0.2.0
[EGL] Target ref: main
[EGL] Install directory: /home/.../Evgenium_GPT
```

The bootstrapper installs/checks base OS dependencies, clones/updates the repository, creates the private Python environment, installs EGL, downloads the Playwright Chromium build, runs diagnostics, then starts the interactive ChatGPT setup only when the machine is not already configured.

### Arch Linux dependency note

On Arch the required bootstrap packages are currently:

```text
git python python-pip portaudio
```

`libpulse` is **optional** and supplies `pactl`/`parec` for making the orb react to output volume. Failure to install the optional audio-meter dependency does **not** abort EGL installation.

EGL does **not** try to install a nonexistent Arch package named `pulseaudio-utils`.

## Main EGL directory

Almost everything lives in one place:

```text
~/Evgenium_GPT/
├── .git/
├── .venv/
├── config/
│   └── config.json
├── data/
│   ├── browser-profile/
│   └── models/
├── state/
├── src/
├── bootstrap.sh
└── install.sh
```

Only the normal Linux integration files live elsewhere:

```text
~/.config/systemd/user/egl.service
~/.local/bin/egl
```

Temporary IPC can live in `$XDG_RUNTIME_DIR/egl`.

A custom home is supported:

```bash
curl -fsSL "https://raw.githubusercontent.com/velikiievgeniusultimate/Evgenium_GPT_LIVE/refs/heads/main/bootstrap.sh?$(date +%s)" | EGL_HOME="$HOME/My_EGL" bash
```

The selected `EGL_HOME` is written into the generated systemd user service so it survives reboots.

## First setup

On the first successful install EGL will:

1. run `egl doctor` to verify Python modules, Playwright Chromium and audio availability;
2. download the small Russian Vosk model;
3. show microphone devices;
4. open a visible dedicated Chromium profile;
5. let you sign in to ChatGPT once;
6. ask you to open the exact chat EGL should always reuse;
7. remember its URL and browser profile;
8. install/start `egl.service` as a systemd user service.

No ChatGPT password is stored by EGL itself. Authentication remains in the dedicated browser profile.

Running the curl installer again behaves as an **update**: if a valid `config.json` with a remembered chat exists, EGL updates dependencies/code, runs diagnostics, refreshes the service and skips the interactive login/chat-selection wizard.

## Commands

```bash
egl doctor              # dependency/browser/audio/config diagnostics
egl status              # current daemon state
egl wake                # manually start Voice
egl stop                # force-stop Voice
egl service status
egl service restart
egl service logs        # follow journal logs
egl setup               # intentionally re-run chat/login setup
```

## Architecture

```text
microphone
   │
   ├── Vosk local phrase detector
   │      ├── «Евгениум слушай»
   │      └── «Евгениум стоп»
   │
   ▼
EGL daemon
   ├── Playwright Chromium + dedicated profile
   │      └── remembered chatgpt.com conversation
   │             └── ChatGPT Voice
   │
   └── live orb
          ├── always-visible session state
          └── optional pactl/parec output meter
```

Only the wake/stop phrase detector is local. Normal conversation is handled by ChatGPT Voice in Chromium.

## Live orb

The orb is separate from the browser:

- starting state while Voice is being opened;
- active state while EGL considers Voice live;
- error state if browser automation fails;
- breathing animation so there is always a visible live-session signal;
- when `parec` is available, its size also follows default desktop output volume.

The current meter watches the default output sink, so other sounds can also make the orb pulse. Isolating only the Chromium stream is a later improvement.

## About «Евгениум» recognition

The configured phrases are exactly:

```text
Евгениум слушай
Евгениум стоп
```

The MVP uses Vosk with a restricted Russian grammar. Because «Евгениум» is invented, a few acoustic aliases such as «Евгений» are accepted internally. The hotword layer is isolated so it can later be replaced with a purpose-trained wake-word model without rewriting browser control.

## Browser automation caveat

ChatGPT Web does not expose EGL with a public `startVoice()` API. EGL therefore controls the normal Voice/Exit buttons through Playwright selectors in `src/egl/browser.py`. A substantial ChatGPT UI change can require a selector update.

The runtime currently uses Playwright's Chromium channel in headless mode and explicitly removes Playwright's default `--mute-audio` argument. The first setup is headed so login and chat selection are visible.

## Diagnostics

If anything breaks, start with:

```bash
egl doctor
egl service status
egl service logs
```

`egl doctor` distinguishes blocking failures from optional warnings. In particular, missing `pactl`/`parec` is only a warning.

The installer also performs imports of `playwright`, `vosk`, `sounddevice` and `PySide6` before setup and checks that the Playwright Chromium executable actually exists.

## CI

`.github/workflows/ci.yml` tests the package on clean Ubuntu runners with Python 3.11 and Python 3.14, runs unit tests/compile checks, imports all runtime Python dependencies and performs a persistent-context Playwright Chromium smoke launch.

## Development

Fast local checks:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests
bash -n bootstrap.sh install.sh
```

Editable install:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
python -m playwright install chromium
egl doctor
egl setup --no-service
```

## License

MIT.
