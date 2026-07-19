from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from . import cli
from .bootstrap import BootstrapError, doctor, import_native_tools, setup_tools, verify_lock

PUBLIC_BOOTSTRAP_COMMANDS = ("setup", "doctor", "import-native", "verify-tools")


def package_version() -> str:
    try:
        return version("orbisstudio")
    except PackageNotFoundError:
        return "0+unknown"


def _bootstrap_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orbis")
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version()}")
    commands = parser.add_subparsers(dest="command", required=True)

    setup = commands.add_parser("setup", help="Install the managed Android toolchain")
    setup.add_argument("--tools-dir")
    setup.add_argument("--force", action="store_true")

    check = commands.add_parser("doctor", help="Diagnose the Android toolchain")
    check.add_argument("--tools-dir")
    check.add_argument("--scope", choices=("core", "full"), default="full")

    native = commands.add_parser(
        "import-native",
        help="Import locally obtained native tools and record their SHA-256 hashes",
    )
    native.add_argument("--from", dest="source", required=True)
    native.add_argument("--tools-dir")

    lock = commands.add_parser(
        "verify-tools",
        help="Verify managed tools against toolchain.lock.json",
    )
    lock.add_argument("--tools-dir")
    return parser


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "--version":
        print(f"orbis {package_version()}")
        return

    if len(sys.argv) < 2 or sys.argv[1] not in PUBLIC_BOOTSTRAP_COMMANDS:
        cli.main()
        return

    args = _bootstrap_parser().parse_args()
    directory = Path(args.tools_dir) if args.tools_dir else None
    try:
        if args.command == "setup":
            report = setup_tools(directory, force=args.force)
        elif args.command == "doctor":
            report = doctor(directory, scope=args.scope)
        elif args.command == "import-native":
            report = import_native_tools(Path(args.source), directory)
        else:
            report = verify_lock(directory)
        print(report.to_json())
        raise SystemExit(0 if report.ready else 2)
    except BootstrapError as error:
        raise SystemExit(f"Orbis setup error: {error}") from error


if __name__ == "__main__":
    main()
