#!/usr/bin/env bash
set -Eeuo pipefail

BOOTSTRAP_VERSION="0.5.4"
REPO_URL="https://github.com/velikiievgeniusultimate/Evgenium_GPT_LIVE.git"
EGL_REF="${EGL_REF:-main}"
EGL_HOME="${EGL_HOME:-$HOME/Evgenium_GPT}"

say() { printf '\033[1;36m[EGL]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[EGL WARN]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[EGL ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

on_error() {
  local rc=$?
  printf '\033[1;31m[EGL ERROR]\033[0m bootstrap v%s failed near line %s (exit %s).\n' "$BOOTSTRAP_VERSION" "${BASH_LINENO[0]:-?}" "$rc" >&2
  printf 'Re-run the same installer after the issue is fixed; it is designed to resume safely.\n' >&2
  exit "$rc"
}
trap on_error ERR

run_root() {
  if (( EUID == 0 )); then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    die "Root privileges are required to install system packages, but sudo is not available."
  fi
}

has_system_browser() {
  local name
  for name in chromium chromium-browser google-chrome-stable google-chrome brave-browser brave vivaldi-stable vivaldi; do
    command -v "$name" >/dev/null 2>&1 && return 0
  done
  [[ -n "${EGL_BROWSER:-}" && -x "${EGL_BROWSER:-}" ]]
}

install_system_deps() {
  if [[ "${EGL_SKIP_SYSTEM_DEPS:-0}" == "1" ]]; then
    say "Skipping system dependency installation (EGL_SKIP_SYSTEM_DEPS=1)."
    return
  fi

  say "Checking/installing required Linux dependencies (sudo may ask for your password)..."

  if command -v pacman >/dev/null 2>&1; then
    run_root pacman -S --needed --noconfirm git python python-pip portaudio xorg-server-xvfb

    if ! has_system_browser; then
      say "No normal Chromium-family browser found; installing Arch Chromium."
      run_root pacman -S --needed --noconfirm chromium
    fi

    if ! command -v pactl >/dev/null 2>&1 || ! command -v parec >/dev/null 2>&1; then
      run_root pacman -S --needed --noconfirm libpulse || warn "Could not install libpulse; EGL will work, but the orb may not react to output volume."
    fi

  elif command -v apt-get >/dev/null 2>&1; then
    run_root apt-get update
    run_root apt-get install -y git python3 python3-venv python3-pip libportaudio2 xvfb
    if ! has_system_browser; then
      warn "No supported Chromium-family browser detected. Install Chromium/Chrome before EGL setup or set EGL_BROWSER=/path/to/browser."
    fi
    if ! command -v pactl >/dev/null 2>&1 || ! command -v parec >/dev/null 2>&1; then
      run_root apt-get install -y pulseaudio-utils || warn "Could not install pulseaudio-utils; the audio-reactive orb is optional."
    fi

  elif command -v dnf >/dev/null 2>&1; then
    run_root dnf install -y git python3 python3-pip portaudio xorg-x11-server-Xvfb
    if ! has_system_browser; then
      warn "No supported Chromium-family browser detected. Install Chromium/Chrome before EGL setup or set EGL_BROWSER=/path/to/browser."
    fi
    if ! command -v pactl >/dev/null 2>&1 || ! command -v parec >/dev/null 2>&1; then
      run_root dnf install -y pulseaudio-utils || warn "Could not install pulseaudio-utils; the audio-reactive orb is optional."
    fi

  else
    warn "Unknown package manager. Continuing if git, Python, PortAudio, Xvfb and a Chromium-family browser are already available."
  fi
}

say "Evgenium GPT LIVE bootstrap v$BOOTSTRAP_VERSION"
say "Target ref: $EGL_REF"
say "Install directory: $EGL_HOME"

install_system_deps
command -v git >/dev/null 2>&1 || die "git is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required"
command -v Xvfb >/dev/null 2>&1 || die "Xvfb is required for EGL's invisible runtime browser."
has_system_browser || die "A normal Chromium-family browser is required. Install Chromium/Chrome or set EGL_BROWSER=/path/to/browser."

if [[ -d "$EGL_HOME/.git" ]]; then
  say "Existing EGL checkout found; updating it."
  if [[ -n "$(git -C "$EGL_HOME" status --porcelain)" ]]; then
    die "$EGL_HOME contains uncommitted changes. Commit/stash them and run the installer again."
  fi
  git -C "$EGL_HOME" fetch --prune origin "$EGL_REF"
  git -C "$EGL_HOME" checkout "$EGL_REF"
  git -C "$EGL_HOME" reset --hard "origin/$EGL_REF"
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

say "Checkout: $(git -C "$EGL_HOME" rev-parse --short HEAD)"
export EGL_HOME
exec bash "$EGL_HOME/install.sh"
