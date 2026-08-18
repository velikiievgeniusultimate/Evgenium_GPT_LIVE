#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EGL_HOME="${EGL_HOME:-$HOME/Evgenium_GPT}"
VENV="$EGL_HOME/.venv"
BIN_DIR="$HOME/.local/bin"

say() { printf '\033[1;36m[EGL]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[EGL ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || die "python3 is required"
mkdir -p "$EGL_HOME" "$BIN_DIR"

SYSTEM_PY="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
say "System Python: $(python3 --version 2>&1)"

# Arch is rolling-release. A venv created by an older Python minor version can
# silently become unusable after a system upgrade, so rebuild only when needed.
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

say "Installing compatible Playwright Chromium"
"$VENV/bin/python" -m playwright install chromium

say "Checking Playwright browser"
"$VENV/bin/python" - <<'PY'
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    path = Path(p.chromium.executable_path)
    if not path.exists():
        raise SystemExit(f"Playwright Chromium executable is missing: {path}")
    print(f"  OK Chromium: {path}")
PY

ln -sfn "$VENV/bin/egl" "$BIN_DIR/egl"

export EGL_HOME
export PATH="$BIN_DIR:$PATH"

say "EGL files live in: $EGL_HOME"
say "CLI installed as: $BIN_DIR/egl"
say "Running EGL doctor before interactive setup"
"$VENV/bin/egl" doctor

echo
exec "$VENV/bin/egl" setup
