# Evgenium GPT LIVE — EGL

**EGL** turns the regular ChatGPT **Web Voice** session into a Linux-native voice assistant with local wake/stop phrases, a persistent authenticated browser profile, Plasma integration, autostart and a live desktop orb.

Current version: **0.4.0**. Arch Linux + KDE Plasma is the primary target.

## What it should feel like

- say **«Евгениум слушай»** → EGL starts Voice in one remembered ChatGPT chat;
- talk normally to ChatGPT;
- while Voice is active, the live orb appears in the bottom-left corner;
- say **«Евгениум стоп»** → EGL locally terminates Voice;
- the service Chromium normally stays out of the taskbar, pager and Alt+Tab;
- open **Evgenium GPT LIVE** from the application launcher when you actually want settings or the service browser.

## One-line install / update

```bash
curl -fsSL "https://raw.githubusercontent.com/velikiievgeniusultimate/Evgenium_GPT_LIVE/refs/heads/main/bootstrap.sh?$(date +%s)" | bash
```

You should see:

```text
[EGL] Evgenium GPT LIVE bootstrap v0.4.0
[EGL] Target ref: main
[EGL] Install directory: /home/.../Evgenium_GPT
```

Almost everything remains under `~/Evgenium_GPT`.

## EGL 0.4 boot/network behavior

The daemon is now deliberately **network-independent at startup**.

At Plasma login only these local pieces start:

```text
systemd --user
      ↓
EGL daemon
      ├── Vosk wake/stop listener
      ├── local control socket
      └── live-orb service
```

**Chromium is not launched at login.** Internet/VPN is not a systemd dependency.

Only after **«Евгениум слушай»** does EGL launch the dedicated Chromium profile and attempt to open ChatGPT Voice. If ChatGPT cannot be reached, EGL:

1. shows an error state/desktop notification;
2. closes the failed service browser;
3. returns to local wake-word waiting;
4. **does not repeatedly retry the network request in a loop**.

When VPN/network becomes available, say **«Евгениум слушай»** again.

The microphone listener has its own bounded retry loop (2 seconds up to 30 seconds), so a late PipeWire/audio device during login does not require restarting EGL.

`egl.service` restarts on genuine daemon crashes, but systemd limits repeated crashes to 5 starts in 5 minutes instead of spinning forever.

## KDE Plasma hidden service browser

Runtime Chromium starts with the Linux window class `EvgeniumGPT` and `--start-minimized`.

EGL installs a tiny KWin script:

```text
~/.local/share/kwin/scripts/eglwindowguard/
```

It matches **only** the EGL-specific Chromium class and sets:

- `skipTaskbar`;
- `skipPager`;
- `skipSwitcher`;
- minimized state.

So normal Chromium/Chrome windows are not affected.

You can explicitly reveal or hide the service browser:

```bash
egl browser show
egl browser hide
```

The GUI exposes the same controls.

## GUI settings

The installer adds **Evgenium GPT LIVE** to the Plasma application menu. You can also run:

```bash
egl gui
```

The current GUI includes:

- daemon/systemd state;
- manual Voice start/stop;
- show/hide service Chromium;
- microphone selection;
- live microphone level test;
- enable/disable the live orb;
- orb size;
- background/hidden Chromium toggle;
- keep Chromium alive after a completed Voice conversation;
- remembered ChatGPT chat URL;
- save + automatic EGL service restart.

New installs use the **system default microphone** during setup. Device selection is intentionally moved to the GUI.

## First setup and authentication

EGL uses a normal system Chromium-family browser with a dedicated clean profile. During the human login/Cloudflare flow, Playwright is **not attached**. After you log in and open the desired chat, EGL attaches via the local DevTools/CDP endpoint and remembers that chat.

EGL does not attempt to bypass CAPTCHA or Cloudflare verification.

On Arch, if Chromium/Chrome/Brave/Vivaldi is not already installed, the bootstrap installs `chromium`.

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
├── kde/
│   └── kwin/eglwindowguard/
├── state/
├── src/
├── bootstrap.sh
└── install.sh
```

Linux integration files intentionally live in their standard locations:

```text
~/.config/systemd/user/egl.service
~/.local/bin/egl
~/.local/share/applications/egl-settings.desktop
~/.local/share/kwin/scripts/eglwindowguard/
```

Temporary IPC can live in `$XDG_RUNTIME_DIR/egl`.

## Commands

```bash
egl gui                 # settings application
egl doctor              # dependency/autostart/Plasma diagnostics
egl status              # current daemon state
egl wake                # manually start Voice
egl stop                # force-stop Voice
egl browser show        # reveal dedicated Chromium
egl browser hide        # minimize it again
egl integration status
egl service status
egl service restart
egl service logs
egl setup               # intentionally re-run ChatGPT login/chat selection
```

## Live orb

The orb is independent of Chromium:

- starting state while Voice is opening;
- active state while Voice is live;
- error state if browser/network automation fails;
- breathing animation at minimum;
- when `parec` is available, its size follows default desktop output volume.

The current audio meter watches the default output sink, not only ChatGPT audio.

## About «Евгениум» recognition

The configured phrases are:

```text
Евгениум слушай
Евгениум стоп
```

Vosk uses a very restricted Russian grammar. A few acoustic aliases such as «Евгений» are accepted internally because «Евгениум» is invented. The hotword layer is isolated from browser control.

## Browser automation caveat

ChatGPT Web does not expose EGL with a public `startVoice()` API. EGL therefore controls the normal Voice/Exit UI through DOM selectors in `src/egl/browser.py`.

The browser process itself is launched directly as a normal system Chromium-family browser. Playwright is only the local CDP control client.

## Diagnostics and reboot test

After an update:

```bash
egl doctor
systemctl --user status egl.service
```

For the real reboot test:

1. update to the latest `main`;
2. leave VPN **off**;
3. reboot/login to Plasma;
4. run `egl status` — it should report `idle` without Chromium being visible;
5. say **«Евгениум слушай»** while VPN is off — EGL should fail once and return to idle;
6. enable VPN;
7. say **«Евгениум слушай»** again — Voice should start without restarting the daemon.

## CI

`.github/workflows/ci.yml` checks Python 3.11 and 3.14, shell/JSON/KWin-JavaScript syntax, imports the GUI/runtime modules, runs unit tests/compile checks and performs a normal-Chromium CDP smoke test under Xvfb.

## Development

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests
bash -n bootstrap.sh install.sh
```

## License

MIT.
