# Evgenium GPT LIVE — EGL

**EGL** turns the regular ChatGPT **Web Voice** session into a Linux-native voice assistant with local wake/stop phrases, a persistent authenticated browser profile, autostart, GUI settings, live debugging and a desktop orb.

Current version: **0.5.4**. Arch Linux + KDE Plasma is the primary target.

## What it should feel like

- EGL starts with the desktop and immediately keeps one authenticated ChatGPT tab alive in the background;
- that Chromium window lives on a **private Xvfb virtual display**, so Plasma never sees it;
- say **«Евгениум слушай»** → EGL clicks Voice in the already-loaded tab;
- say **«Евгениум стоп»** → EGL aggressively terminates Voice but keeps Chromium/profile alive;
- open **Evgenium GPT LIVE** from the application launcher for settings and debugging.

## One-line install / update

```bash
curl -fsSL "https://raw.githubusercontent.com/velikiievgeniusultimate/Evgenium_GPT_LIVE/refs/heads/main/bootstrap.sh?$(date +%s)" | bash
```

You should see:

```text
[EGL] Evgenium GPT LIVE bootstrap v0.5.4
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

## Strict wake / aggressive STOP

EGL treats wake and stop very differently.

### Wake

Wake is conservative:

- **partial Vosk results can never start Voice**;
- the phrase must appear in a final Vosk result;
- Vosk word confidences are enabled and the minimum confidence of all decoded words must pass the configured threshold;
- default wake threshold: **86%**;
- matching is exact against the decoder phrase, not fuzzy/suffix matching.

### Why «Евгениум» uses an internal acoustic surrogate

`Евгениум` is intentionally an invented word. Stock Vosk Russian models may not contain it in their vocabulary. Runtime Vosk grammars silently ignore words that are missing from the model vocabulary, which made the literal strict phrase impossible to decode in EGL 0.5.2/0.5.3.

EGL 0.5.4 keeps **«Евгениум слушай»** and **«Евгениум стоп»** as the user-facing commands, but checks the Vosk vocabulary at startup. If `евгениум` is out-of-vocabulary, EGL maps only that token to the explicit acoustic surrogate `евгений` for the decoder:

```text
User says / GUI shows:  евгениум слушай
Vosk decoder expects:   евгений слушай

User says / GUI shows:  евгениум стоп
Vosk decoder expects:   евгений стоп
```

This does **not** restore the old broad soft aliases: only a phrase that can be represented by the model through an explicit word-level mapping is put into the grammar, and wake still requires a FINAL high-confidence exact match.

`egl doctor` validates this mapping against the installed Vosk model and prints the actual decoder phrases.

### STOP

STOP is intentionally aggressive because a false stop is much less harmful than a Voice session that refuses to die:

- STOP can fire from a **partial** Vosk result while Voice is active;
- audio blocks are reduced to 100 ms for lower detection latency;
- default STOP confidence threshold is only **35%**;
- one STOP is emitted per Voice session;
- STOP has no shared debounce with wake.

Both thresholds and both user-facing phrases are editable in the GUI. Saving settings restarts the EGL daemon so the new Vosk grammar is applied immediately.

## Microphone sample rates

EGL does not force hardware microphones to 16 kHz. USB/pro-audio interfaces may expose only 44.1/48 kHz through PortAudio.

EGL probes the selected input device, picks an accepted native/common sample rate and passes the actual stream rate to Vosk. The GUI microphone test uses the same device/rate resolver, and `egl doctor` reports the selected device and usable rate.

## Aggressive browser STOP pipeline

The browser stop path no longer waits several seconds for ChatGPT to cooperate.

```text
STOP detected
    ↓
Exit click
    ↓  max ~0.55 s
Voice UI gone? ── yes → done
    │ no
    ▼
force navigation to remembered chat
    ↓
still stuck?
    ▼
destroy Voice tab + create replacement tab
```

The last fallback destroys the page that owns the WebRTC session while keeping the same Chromium process, profile and authentication alive. The replacement tab then warms back up in the background.

The daemon also stops waiting for the composer to fully reload before acknowledging STOP: the live orb disappears as soon as STOP reaches the daemon, and page readiness recovery happens separately.

## GUI settings and live debugger

Open **Evgenium GPT LIVE** from Plasma or run:

```bash
egl gui
```

The main GUI includes:

- daemon/systemd state;
- manual Voice start and emergency STOP;
- manual reload of the permanent hidden ChatGPT tab;
- microphone selection and live level test;
- editable wake and STOP phrases;
- wake confidence threshold;
- STOP confidence threshold;
- live orb settings;
- **Открыть отладчик** button.

The debugger shows the full recognition/stop pipeline. For each Vosk hypothesis it shows:

- recognized text;
- final vs partial;
- word-confidence floor;
- `wake_match` / `stop_match`;
- whether it was accepted;
- rejection/acceptance reason.

STOP has its own prominent status line:

```text
STOP: DETECTED → SENT → CONFIRMED
method=exit_click | 143 ms | UI after=false
```

or, when ChatGPT resists:

```text
STOP: DETECTED → SENT → CONFIRMED
method=forced_navigation | 721 ms | UI after=false
```

and the final destructive fallback is reported as `tab_replaced`.

Debug data is stored under:

```text
~/Evgenium_GPT/state/debug.jsonl
~/Evgenium_GPT/state/debug-browser.png
```

## VPN / network resilience

The Chromium process and tab stay alive even when ChatGPT is unreachable.

If EGL starts while VPN is off:

1. Xvfb and Chromium still start;
2. the remembered ChatGPT tab remains open;
3. EGL retries loading the same tab with backoff up to 60 seconds;
4. it does not repeatedly kill/relaunch Chromium;
5. when VPN becomes available, the readiness loop discovers the Voice button and moves to `idle_ready`.

If Chromium or Xvfb genuinely crashes, EGL restarts that browser stack with bounded backoff.

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
egl doctor              # dependency/autostart/browser/mic/Vosk-grammar diagnostics
egl status              # idle_ready / idle_loading / listening / ...
egl wake                # manual start bypassing speech recognition
egl stop                # aggressive emergency STOP
egl browser reload      # force-reload the permanent hidden tab
egl service status
egl service restart
egl service logs
egl setup               # intentionally re-run ChatGPT login/chat selection
```

## Browser automation caveat

ChatGPT Web does not expose EGL with a public `startVoice()` / `stopVoice()` API. EGL controls the normal Voice/Exit UI through DOM selectors in `src/egl/browser.py`.

Because STOP has destructive navigation/tab-replacement fallbacks, a changed Exit selector should no longer leave a Voice session running indefinitely.

## Reboot / command test

After updating:

```bash
egl --version
egl doctor
egl status
```

Expected `doctor` output includes the selected mic rate and representable Vosk command phrases, for example:

```text
[OK] Selected microphone: Audient iD4 (..., 48000 Hz mono/int16)
[OK] Wake decoder phrase(s): евгений слушай
[OK] STOP decoder phrase(s): евгений стоп
```

Then:

1. open the GUI debugger;
2. speak ordinary background phrases for a while — partial wake observations must not trigger Voice;
3. say **«Евгениум слушай»** clearly — debugger should eventually show the decoder surrogate with a final result above the wake threshold followed by `WAKE_ACCEPTED`;
4. while Voice is active say **«Евгениум стоп»**;
5. the orb should disappear immediately;
6. debugger should show `STOP_DETECTED → STOP_SENT → STOP_CONFIRMED`;
7. inspect `stop_method` and `total_stop_ms` to see exactly how ChatGPT was terminated.

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
