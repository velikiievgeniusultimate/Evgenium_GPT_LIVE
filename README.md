# Evgenium GPT LIVE — EGL

**EGL** turns the regular ChatGPT **Web Voice** session into a Linux-native voice assistant with local wake/stop phrases, a persistent authenticated browser profile, autostart, GUI settings and a live desktop orb.

Current version: **0.5.0**. Arch Linux + KDE Plasma is the primary target.

## What it should feel like

- EGL starts with the desktop and immediately keeps one authenticated ChatGPT tab alive in the background;
- that Chromium window lives on a **private Xvfb virtual display**, so Plasma never sees it;
- say **«Евгениум слушай»** → EGL clicks Voice in the already-loaded tab;
- say **«Евгениум стоп»** → EGL exits Voice but keeps the same Chromium process and chat tab alive;
- the next wake therefore does not race page startup/loading;
- open **Evgenium GPT LIVE** from the application launcher when you want settings.

## One-line install / update

```bash
curl -fsSL "https://raw.githubusercontent.com/velikiievgeniusultimate/Evgenium_GPT_LIVE/refs/heads/main/bootstrap.sh?$(date +%s)" | bash
```

You should see:

```text
[EGL] Evgenium GPT LIVE bootstrap v0.5.0
[EGL] Target ref: main
[EGL] Install directory: /home/.../Evgenium_GPT
```

Almost everything remains under `~/Evgenium_GPT`.

## Permanent hidden browser

EGL 0.5 deliberately separates **browser lifetime** from **Voice lifetime**:

```text
Plasma login
    ↓
systemd --user
    ↓
EGL daemon
    ├── Vosk wake/stop listener
    ├── permanent Xvfb server (private display, e.g. :90)
    └── permanent system Chromium
            └── remembered chatgpt.com chat
                    └── Voice button already waiting
```

The runtime Chromium is a normal headed browser because WebRTC/audio reliability matters, but it renders into Xvfb rather than the real Plasma/Wayland display. There is therefore no service-browser taskbar entry, Alt+Tab entry, Overview window or startup flash.

The visible browser is used only by `egl setup`, when the user intentionally needs to log in or choose another chat.

## VPN / network resilience

The Chromium process and its tab are local and stay alive even when ChatGPT is unreachable.

If EGL starts while VPN is off:

1. Xvfb and Chromium still start normally;
2. the remembered ChatGPT tab remains open;
3. EGL periodically retries **loading the page in the same tab** with backoff up to 60 seconds;
4. it does **not** repeatedly kill/relaunch Chromium;
5. when VPN becomes available, the background readiness loop discovers the Voice button and moves to `idle_ready`.

An explicit **«Евгениум слушай»** also performs one immediate readiness attempt. If ChatGPT is still unavailable, EGL shows an error/notification but leaves the hidden browser alive and continues recovering in the background.

If Chromium or Xvfb genuinely crashes, EGL restarts that browser stack with bounded backoff.

## Why Xvfb instead of merely minimizing Chromium

KWin rules can hide a window from taskbar/pager/switcher, but they cannot guarantee zero visible startup flash on every Wayland/Chromium combination.

EGL 0.5 therefore moves runtime Chromium completely off the real desktop. The older KWin integration remains harmless as a fallback/legacy integration, but the normal runtime window never reaches KWin at all.

On Arch the installer adds:

```text
xorg-server-xvfb
```

## GUI settings

The installer adds **Evgenium GPT LIVE** to the Plasma application menu. You can also run:

```bash
egl gui
```

The GUI currently includes:

- daemon/systemd state;
- manual Voice start/stop;
- manual reload of the permanent hidden ChatGPT tab;
- microphone selection;
- live microphone level test;
- enable/disable the live orb;
- orb size;
- remembered ChatGPT chat URL;
- save + automatic EGL service restart.

The runtime-browser policy is intentionally no longer a toggle: **it is always permanent and always hidden**.

## First setup and authentication

EGL uses a normal visible system Chromium-family browser for first authentication. During the human login/Cloudflare flow Playwright is **not attached**. After you log in and open the desired chat, EGL attaches through the local DevTools/CDP endpoint, remembers that chat and closes the setup browser.

After that, the systemd daemon opens the same persistent profile on the private Xvfb display.

EGL does not attempt to bypass CAPTCHA or Cloudflare verification.

## Files

```text
~/Evgenium_GPT/
├── .git/
├── .venv/
├── config/
│   └── config.json
├── data/
│   ├── browser-profile-system/
│   └── models/
├── state/
├── src/
├── bootstrap.sh
└── install.sh
```

Standard Linux integration files live in their normal locations:

```text
~/.config/systemd/user/egl.service
~/.local/bin/egl
~/.local/share/applications/egl-settings.desktop
```

Temporary IPC can live in `$XDG_RUNTIME_DIR/egl`.

## Commands

```bash
egl gui                 # settings application
egl doctor              # dependency/autostart/browser diagnostics
egl status              # idle_ready / idle_loading / listening / ...
egl wake                # manually start Voice
egl stop                # force-stop Voice
egl browser reload      # force-reload the permanent hidden tab
egl service status
egl service restart
egl service logs
egl setup               # intentionally re-run ChatGPT login/chat selection
```

`egl browser show/hide` are retained only for 0.4 CLI compatibility; the 0.5 runtime browser lives on a private display and is intentionally not exposable to Plasma.

## Live orb

The orb is independent of Chromium:

- starting state while Voice is being entered;
- active state while Voice is live;
- error state when Voice cannot be entered;
- breathing animation at minimum;
- when `parec` is available, its size follows default desktop output volume.

## About «Евгениум» recognition

The configured phrases are:

```text
Евгениум слушай
Евгениум стоп
```

Vosk uses a restricted Russian grammar. A few acoustic aliases such as «Евгений» are accepted internally because «Евгениум» is invented. The hotword layer is isolated from browser control.

## Browser automation caveat

ChatGPT Web does not expose EGL with a public `startVoice()` API. EGL controls the normal Voice/Exit UI through DOM selectors in `src/egl/browser.py`.

The important 0.5 change is that those selectors now operate on an already-loaded long-lived page. `start_voice()` also waits for the Voice button before clicking, so a slow render no longer produces the old startup race.

## Reboot / VPN test

After updating:

```bash
egl --version
egl doctor
egl status
```

Expected test:

1. leave VPN **off** and reboot;
2. after Plasma login, no Chromium window should ever appear;
3. `egl status` should show `idle_loading` or `idle_ready` rather than a dead service;
4. enable VPN without restarting EGL;
5. within the background retry interval, status should become `idle_ready`;
6. say **«Евгениум слушай»** — Voice should start from the already-running tab;
7. say **«Евгениум стоп»** — Voice stops, but hidden Chromium remains alive;
8. call again — there should be no browser startup flash or page-load race.

## CI

`.github/workflows/ci.yml` checks Python 3.11 and 3.14, shell/JSON/KWin-JavaScript syntax, GUI/runtime imports, unit tests/compile checks and a smoke test that lets **EGL itself** create a private Xvfb server, launch system Chromium on it and attach through CDP.

## Development

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests
bash -n bootstrap.sh install.sh
```

## License

MIT.
