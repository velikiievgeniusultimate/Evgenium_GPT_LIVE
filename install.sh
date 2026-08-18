#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EGL_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/egl"
VENV="$EGL_HOME/venv"

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/pip" install "$ROOT_DIR"

echo "Installing Playwright Chromium..."
"$VENV/bin/python" -m playwright install chromium

echo
exec "$VENV/bin/egl" setup
