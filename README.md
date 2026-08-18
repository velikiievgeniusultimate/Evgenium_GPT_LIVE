# Evgenium GPT LIVE — EGL

**EGL** is a Linux helper around the regular ChatGPT **Web Voice** session. It keeps the intelligence in the normal web product and adds Linux-native wake/stop phrases, a persistent browser profile, autostart and a live desktop orb.

Current version: **0.3.0** (early MVP, Arch/KDE is the primary target).

## What it should feel like

- say **«Евгениум слушай»** → EGL starts Voice in one remembered ChatGPT chat;
- talk normally to ChatGPT;
- while Voice is active, a live orb appears in the bottom-left corner;
- say **«Евгениум стоп»** → EGL locally terminates the Voice session;
- a dedicated browser profile keeps the ChatGPT login between restarts.

## One-line install

```bash
curl -fsSL "https://raw.githubusercontent.com/velikiievgeniusultimate/Evgenium_GPT_LIVE/refs/heads/main/bootstrap.sh?$(date +%s)" | bash
```

You should see:

```text
[EGL] Evgenium GPT LIVE bootstrap v0.3.0
[EGL] Target ref: main
[EGL] Install directory: /home/.../Evgenium_GPT
```

The cache-busting query is intentional so repeated installs fetch the current `main` bootstrap instead of a recently cached raw GitHub response.

## Arch Linux

Required bootstrap packages:

```text
git python python-pip portaudio
```

EGL 0.3 requires a **normal Chromium-family browser**. If none of Chromium, Chrome, Brave or Vivaldi is found, the Arch bootstrap installs `chromium` automatically.

`libpulse` is optional and supplies `pactl`/`parec` for making the orb react to output volume. Failure to install it does not abort EGL.

## Why EGL 0.3 uses the system browser

Older EGL builds launched Playwright's downloaded Chrome for Testing directly. That is convenient for automation but is a bad fit for ChatGPT authentication: Cloudflare can challenge test/automation browsers aggressively.

EGL 0.3 instead does this:

```text
system Chromium/Chrome
        │
        ├── dedicated clean EGL profile
        ├── human performs Cloudflare/login normally
        │
        └── after login, EGL attaches through DevTools/CDP
                 │
                 └── Playwright controls only ChatGPT Voice/Exit UI
```

During the first login **Playwright is not attached to the page at all**. EGL waits until you have completed verification, signed in and opened the desired chat. Only after you return to the terminal and press Enter does EGL attach through CDP and remember the chat URL.

EGL does not attempt to bypass CAPTCHA or Cloudflare checks.

## Main EGL directory

Almost everything lives here:

```text
~/Evgenium_GPT/
├── .git/
├── .venv/
├── config/
│   └── config.json
├── data/
│   ├── browser-profile-system/   normal Chromium/Chrome profile
│   ├── browser-profile/          old 0.2 test-browser profile, if present
│   └── models/
├── state/
├── src/
├── bootstrap.sh
└── install.sh
```

Only normal Linux integration files live elsewhere:

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

On first successful install EGL will:

1. run `egl doctor`;
2. download the small Russian Vosk model;
3. show microphone devices;
4. launch a **normal system Chromium/Chrome** with EGL's clean dedicated profile;
5. leave the browser completely under your control for Cloudflare/login;
6. ask you to open the exact chat EGL should always reuse;
7. after you press Enter, attach through CDP and remember that chat URL;
8. install/start `egl.service` as a systemd user service.

No ChatGPT password is stored by EGL itself. Authentication remains in the dedicated browser profile.

Running the curl installer again behaves as an update: if a valid `config.json` with a remembered chat exists, EGL updates code/dependencies, refreshes the service and skips interactive login/chat selection.

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
   ├── normal system Chromium/Chrome
   │      ├── dedicated persistent profile
   │      ├── local DevTools endpoint
   │      └── Playwright CDP attachment
   │             └── remembered ChatGPT conversation
   │                    └── ChatGPT Voice
   │
   └── live orb
          ├── always-visible session state
          └── optional pactl/parec output meter
```

Only the wake/stop detector is local. Normal conversation is handled by ChatGPT Voice in the browser.

## Live orb

- starting state while Voice is being opened;
- active state while EGL considers Voice live;
- error state if browser automation fails;
- breathing animation so there is always a visible live-session signal;
- when `parec` is available, its size also follows default desktop output volume.

The current meter watches the default output sink, so other sounds can also make the orb pulse.

## About «Евгениум» recognition

The configured phrases are exactly:

```text
Евгениум слушай
Евгениум стоп
```

The MVP uses Vosk with a restricted Russian grammar. Because «Евгениум» is invented, a few acoustic aliases such as «Евгений» are accepted internally. The hotword layer is isolated so it can later be replaced without rewriting browser control.

## Browser automation caveat

ChatGPT Web does not expose EGL with a public `startVoice()` API. EGL therefore controls the normal Voice/Exit buttons through DOM selectors in `src/egl/browser.py`. A substantial ChatGPT UI change can require a selector update.

Normal daemon operation uses a **headed but minimized system browser**, not true headless mode. This is intentional for WebRTC/audio reliability.

You can override the detected browser executable:

```bash
EGL_BROWSER=/usr/bin/chromium egl setup
```

## Diagnostics

```bash
egl doctor
egl service status
egl service logs
```

`egl doctor` checks Python dependencies, the normal system Chromium-family browser, microphone-capable devices, systemd and the optional audio meter tools.

## CI

`.github/workflows/ci.yml` tests Python 3.11 and 3.14, unit tests, compile checks and a smoke test that launches a normal system Chrome/Chromium process and attaches EGL through CDP.

## Development

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
egl doctor
egl setup --no-service
```

## License

MIT.
