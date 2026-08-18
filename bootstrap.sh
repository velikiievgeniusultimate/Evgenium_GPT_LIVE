#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/velikiievgeniusultimate/Evgenium_GPT_LIVE.git"
EGL_REF="${EGL_REF:-agent/egl-linux-mvp}"
EGL_HOME="${EGL_HOME:-$HOME/Evgenium_GPT}"

say() { printf '\033[1;36m[EGL]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[EGL]\033[0m %s\n' "$*" >&2; exit 1; }

install_system_deps() {
  local need=0
  command -v git >/dev/null 2>&1 || need=1
  command -v python3 >/dev/null 2>&1 || need=1

  if (( need == 0 )); then
    return
  fi

  say "Installing required system packages..."
  if command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --needed --noconfirm git python python-pip portaudio pulseaudio-utils
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y git python3 python3-venv python3-pip libportaudio2 pulseaudio-utils
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y git python3 python3-pip portaudio pulseaudio-utils
  else
    die "git/python3 are missing and your package manager is not supported automatically."
  fi
}

install_system_deps
command -v git >/dev/null 2>&1 || die "git is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

say "Install directory: $EGL_HOME"

if [[ -d "$EGL_HOME/.git" ]]; then
  say "Existing EGL checkout found; updating it."
  if [[ -n "$(git -C "$EGL_HOME" status --porcelain)" ]]; then
    die "$EGL_HOME contains uncommitted changes. Commit/stash them and run the installer again."
  fi
  git -C "$EGL_HOME" fetch --prune origin "$EGL_REF"
  git -C "$EGL_HOME" checkout "$EGL_REF"
  git -C "$EGL_HOME" pull --ff-only origin "$EGL_REF"
elif [[ -e "$EGL_HOME" ]]; then
  if [[ -n "$(find "$EGL_HOME" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    die "$EGL_HOME already exists and is not an EGL git checkout. Move it away or set EGL_HOME to another path."
  fi
  rmdir "$EGL_HOME" 2>/dev/null || true
  say "Cloning EGL..."
  git clone --branch "$EGL_REF" --single-branch "$REPO_URL" "$EGL_HOME"
else
  say "Cloning EGL..."
  git clone --branch "$EGL_REF" --single-branch "$REPO_URL" "$EGL_HOME"
fi

export EGL_HOME
exec "$EGL_HOME/install.sh"
