from __future__ import annotations

import argparse
import logging
import subprocess
import sys

from . import __version__
from .control import send_command
from .service import install_service, uninstall_service
from .state import read_state


def _service_action(action: str) -> int:
    return subprocess.call(["systemctl", "--user", action, "egl.service"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="egl", description="Evgenium GPT LIVE")
    parser.add_argument("--version", action="version", version=f"EGL {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="first-time login, chat selection and model setup")
    setup.add_argument("--no-service", action="store_true", help="do not install/start systemd user service")
    sub.add_parser("daemon", help="run EGL in foreground")
    sub.add_parser("wake", help="manually start ChatGPT Voice")
    sub.add_parser("stop", help="manually stop ChatGPT Voice")
    sub.add_parser("status", help="show current EGL state")

    service = sub.add_parser("service", help="manage systemd user service")
    service.add_argument("action", choices=["install", "uninstall", "start", "stop", "restart", "status", "logs"])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "setup":
        from .setup_wizard import run_setup
        return run_setup(install_autostart=not args.no_service)
    if args.command == "daemon":
        from .daemon import run_daemon
        return run_daemon()
    if args.command == "wake":
        try:
            send_command("wake")
            return 0
        except OSError as exc:
            print(f"EGL daemon is not running: {exc}", file=sys.stderr)
            return 1
    if args.command == "stop":
        try:
            send_command("stop")
            return 0
        except OSError as exc:
            print(f"EGL daemon is not running: {exc}", file=sys.stderr)
            return 1
    if args.command == "status":
        state = read_state()
        print(f"{state.mode}: {state.detail}".rstrip(": "))
        return 0
    if args.command == "service":
        if args.action == "install":
            print(install_service(enable=True))
            return 0
        if args.action == "uninstall":
            uninstall_service()
            return 0
        if args.action == "logs":
            return subprocess.call(["journalctl", "--user", "-u", "egl.service", "-f"])
        return _service_action(args.action)
    return 2
