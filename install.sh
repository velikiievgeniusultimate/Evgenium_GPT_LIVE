#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EGL_HOME="${EGL_HOME:-$HOME/Evgenium_GPT}"
VENV="$EGL_HOME/.venv"
BIN_DIR="$HOME/.local/bin"

say() { printf '\033[1;36m[EGL]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[EGL]\033[0m %s\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || die "python3 is required"

mkdir -p "$EGL_HOME" "$BIN_DIR"

say "Creating Python environment in $VENV"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel

say "Installing EGL Python package"
"$VENV/bin/pip" install --upgrade -e "$ROOT_DIR"

say "Installing Playwright Chromium"
"$VENV/bin/python" -m playwright install chromium

ln -sfn "$VENV/bin/egl" "$BIN_DIR/egl"

export EGL_HOME
export PATH="$BIN_DIR:$PATH"

say "EGL files live in: $EGL_HOME"
say "CLI installed as: $BIN_DIR/egl"
echo
exec "$VENV/bin/egl" setup
