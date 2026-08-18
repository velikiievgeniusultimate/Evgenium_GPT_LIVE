#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EGL_HOME="${EGL_HOME:-$HOME/Evgenium_GPT}"
VENV="$EGL_HOME/.venv"
BIN_DIR="$HOME/.local/bin"
CONFIG_FILE="$EGL_HOME/config/config.json"

say() { printf '\033[1;36m[EGL]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[EGL ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

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
  say "Update complete. Open 'Evgenium GPT LIVE' from the application menu or run: egl gui"
  exit 0
fi

echo
if [[ -r /dev/tty ]]; then
  exec "$VENV/bin/egl" setup </dev/tty
fi

die "First-time EGL setup needs an interactive terminal. Run: $VENV/bin/egl setup"
