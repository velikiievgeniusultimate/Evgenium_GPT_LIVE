# Evgenium GPT LIVE — EGL

**EGL** turns the regular ChatGPT **Web Voice** session into a Linux-native voice assistant with local wake/stop phrases, a persistent authenticated browser profile, autostart, GUI settings, live debugging and a desktop orb.

Current version: **0.5.1**. Arch Linux + KDE Plasma is the primary target.

## What it should feel like

- EGL starts with the desktop and immediately keeps one authenticated ChatGPT tab alive in the background;
- that Chromium window lives on a **private Xvfb virtual display**, so Plasma never sees it;
- say **«Евгениум слушай»** → EGL clicks Voice in the already-loaded tab;
- say **«Евгениум стоп»** → EGL exits Voice but keeps the same Chromium process and chat tab alive;
- open **Evgenium GPT LIVE** from the application launcher for settings and debugging.

## One-line install / update

```bash
curl -fsSL "https://raw.githubusercontent.com/velikiievgeniusultimate/Evgenium_GPT_LIVE/refs/heads/main/bootstrap.sh?$(date +%s)" | bash
```

You should see:

```text
[EGL] Evgenium GPT LIVE bootstrap v0.5.1
[EGL] Target ref: main
[EGL] Install directory: /home/.../Evgenium_GPT
```

Almost everything remains under `~/Evgenium_GPT`.

## Permanent hidden browser

EGL separates **browser lifetime** from **Voice lifetime**:

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

The runtime Chromium is a normal headed browser for WebRTC/audio reliability, but it renders into Xvfb instead of the real Plasma/Wayland display. There is therefore no taskbar entry, Alt+Tab entry, Overview window or startup flash.

The visible browser is used only by `egl setup`, when the user intentionally logs in or chooses another chat.

## VPN / network resilience

The Chromium process and tab stay alive even when ChatGPT is unreachable.

If EGL starts while VPN is off:

1. Xvfb and Chromium still start;
2. the remembered ChatGPT tab remains open;
3. EGL retries loading the same tab with backoff up to 60 seconds;
4. it does not repeatedly kill/relaunch Chromium;
5. when VPN becomes available, the readiness loop discovers the Voice button and moves to `idle_ready`.

If Chromium or Xvfb genuinely crashes, EGL restarts that browser stack with bounded backoff.

## GUI settings and live debugger

Open **Evgenium GPT LIVE** from Plasma or run:

```bash
egl gui
```

The main GUI includes:

- daemon/systemd state;
- manual Voice start/stop;
- manual reload of the permanent hidden ChatGPT tab;
- microphone selection;
- live microphone level test;
- live orb settings;
- remembered ChatGPT chat URL;
- **Открыть отладчик** button.

The debugger is specifically meant for diagnosing wake/stop behavior. It shows:

- a live screenshot of the otherwise invisible Xvfb ChatGPT tab;
- current EGL state;
- the last text Vosk recognized;
- whether that text matched wake or stop aliases;
- whether EGL believed Voice was active when the phrase arrived;
- a structured event timeline;
- manual Wake / STOP / Reload / Screenshot controls;
- the result of the last STOP verification.

Example stop trace:

```text
hotword_heard: евгениум стоп {voice_active:true, stop_match:true}
command_received: stop
voice_stop_begin: ... {ui_active_before:true}
voice_stopped: ... {verified:true, ui_active_after:false}
```

Debug data is stored under:

```text
~/Evgenium_GPT/state/debug.jsonl
~/Evgenium_GPT/state/debug-browser.png
```

The log is automatically bounded so it does not grow forever.

## Verified STOP behavior

EGL 0.5.1 no longer treats `stop_voice()` as fire-and-forget.

After receiving STOP it:

1. records the recognized phrase and match result;
2. sends the Exit click;
3. waits for the Voice UI to disappear;
4. if that does not happen, navigates the permanent tab back to the remembered chat as a fallback;
5. verifies the final UI state;
6. writes `verified=true/false` into the debugger;
7. captures a post-stop screenshot.

Manual GUI/CLI STOP is processed even if EGL's internal `voice_active` flag is already false. This makes it useful as both an emergency stop and a way to detect state desynchronization.

## First setup and authentication

EGL uses a normal visible system Chromium-family browser for first authentication. During the human login/Cloudflare flow Playwright is **not attached**. After login and chat selection, EGL attaches through local DevTools/CDP, remembers the chat and closes the setup browser.

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
│   ├── state.json
│   ├── debug.jsonl
│   └── debug-browser.png
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

## Commands

```bash
egl gui                 # settings + debugger
egl doctor              # dependency/autostart/browser diagnostics
egl status              # idle_ready / idle_loading / listening / ...
egl wake                # manually start Voice
egl stop                # force + verify Voice stop
egl browser reload      # force-reload the permanent hidden tab
egl service status
egl service restart
egl service logs
egl setup               # intentionally re-run ChatGPT login/chat selection
```

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

Vosk uses a restricted Russian grammar. A few acoustic aliases such as «Евгений» are accepted internally because «Евгениум» is invented. The debugger exposes exactly what Vosk recognized and which alias matched.

## Browser automation caveat

ChatGPT Web does not expose EGL with a public `startVoice()` API. EGL controls the normal Voice/Exit UI through DOM selectors in `src/egl/browser.py`.

Those selectors operate on an already-loaded long-lived page. `start_voice()` waits for readiness, while `stop_voice()` now verifies the exit and falls back to returning to the remembered chat if needed.

## Reboot / VPN test

After updating:

```bash
egl --version
egl doctor
egl status
```

Expected flow:

1. leave VPN off and reboot;
2. after Plasma login no Chromium window should appear;
3. `egl status` should show `idle_loading` or `idle_ready`;
4. enable VPN without restarting EGL;
5. wait for `idle_ready`;
6. open the GUI debugger;
7. say **«Евгениум слушай»** and watch the event trace + hidden tab preview;
8. say **«Евгениум стоп»**;
9. confirm the debugger shows `stop_match=true`, `verified=true`, `ui_active_after=false` and the screenshot is back on the normal chat page.

## CI

`.github/workflows/ci.yml` checks Python 3.11 and 3.14, GUI/runtime imports, unit tests/compile checks and a smoke test that lets EGL create a private Xvfb server, launch system Chromium on it and attach through CDP.

## Development

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests
bash -n bootstrap.sh install.sh
```

## License

MIT.
