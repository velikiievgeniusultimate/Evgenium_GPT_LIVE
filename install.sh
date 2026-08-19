#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EGL_HOME="${EGL_HOME:-$HOME/Evgenium_GPT}"
VENV="$EGL_HOME/.venv"
BIN_DIR="$HOME/.local/bin"
CONFIG_FILE="$EGL_HOME/config/config.json"

say() { printf '\033[1;36m[EGL]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[EGL WARN]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[EGL ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

service_diagnostics() {
  echo >&2
  warn "egl.service did not become active. Current status:"
  systemctl --user --no-pager --full status egl.service >&2 || true
  echo >&2
  warn "Recent egl.service log:"
  journalctl --user -u egl.service --no-pager -n 80 >&2 || true
}

verify_service_started() {
  # systemctl restart can return before a crashing service has actually failed.
  # Give the daemon a moment to initialize its local listener/browser stack and
  # then fail the installer with useful diagnostics if it is not still active.
  sleep 1.2
  if ! systemctl --user is-active --quiet egl.service; then
    service_diagnostics
    die "egl.service failed after restart. The diagnostics above show the real daemon error."
  fi
}

command -v python3 >/dev/null 2>&1 || die "python3 is required"
mkdir -p "$EGL_HOME" "$BIN_DIR"

SYSTEM_PY="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
say "System Python: $(python3 --version 2>&1)"

if [[ -x "$VENV/bin/python" ]]; then
  VENV_PY="$($VENV/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  if [[ "$VENV_PY" != "$SYSTEM_PY" ]]; then
    say "Python changed ($VENV_PY -> $SYSTEM_PY); rebuilding EGL venv."
    rm -rf "$VENV"
  fi
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  say "Creating Python environment in $VENV"
  python3 -m venv "$VENV"
else
  say "Reusing Python environment in $VENV"
fi

"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel

say "Installing/updating EGL Python package"
"$VENV/bin/python" -m pip install --upgrade -e "$ROOT_DIR"

say "Checking Python dependencies"
"$VENV/bin/python" - <<'PY'
import importlib
mods = ("playwright", "vosk", "sounddevice", "PySide6")
for name in mods:
    importlib.import_module(name)
    print(f"  OK {name}")
PY

ln -sfn "$VENV/bin/egl" "$BIN_DIR/egl"

export EGL_HOME
export PATH="$BIN_DIR:$PATH"

say "EGL files live in: $EGL_HOME"
say "CLI installed as: $BIN_DIR/egl"

say "Installing desktop/KDE integration"
"$VENV/bin/egl" integration install

say "Running EGL doctor"
"$VENV/bin/egl" doctor

if [[ -f "$CONFIG_FILE" ]] && "$VENV/bin/python" - "$CONFIG_FILE" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if cfg.get("chat_url") else 1)
PY
then
  say "Existing ChatGPT configuration detected; skipping interactive setup."
  "$VENV/bin/egl" service install
  # service install already resets failed/start-limit state before restarting.
  # Do it once more here defensively for old unit/install states, then verify
  # the daemon survives initialization instead of reporting a false success.
  systemctl --user reset-failed egl.service || true
  if ! systemctl --user restart egl.service; then
    service_diagnostics
    die "Could not restart egl.service."
  fi
  verify_service_started
  say "Update complete. EGL daemon restarted and is active with the new code."
  say "Open 'Evgenium GPT LIVE' from the application menu or run: egl gui"
  exit 0
fi

echo
if [[ -r /dev/tty ]]; then
  exec "$VENV/bin/egl" setup </dev/tty
fi

die "First-time EGL setup needs an interactive terminal. Run: $VENV/bin/egl setup"
