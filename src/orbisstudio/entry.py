from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from . import cli
from .bootstrap import BootstrapError, doctor, import_native_tools, setup_tools, verify_lock
from .logical_workspace import extract_logical_partitions
from .workspace import WorkspaceError, create_workspace, load_workspace, verify_workspace

PUBLIC_BOOTSTRAP_COMMANDS = ("setup", "doctor", "import-native", "verify-tools")
PUBLIC_WORKSPACE_COMMANDS = (
    "workspace-create",
    "workspace-info",
    "workspace-verify",
    "workspace-extract-logical",
)


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


def _workspace_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orbis")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser(
        "workspace-create",
        help="Create a reproducible firmware workspace from .img and .bin artifacts",
    )
    create.add_argument("--source", required=True)
    create.add_argument("--project", required=True)
    create.add_argument("--name")
    create.add_argument("--copy-to-work", action="store_true")

    info = commands.add_parser("workspace-info", help="Read a firmware workspace manifest")
    info.add_argument("--project", required=True)

    verify = commands.add_parser(
        "workspace-verify",
        help="Verify immutable Stock artifacts against the workspace manifest",
    )
    verify.add_argument("--project", required=True)

    extract = commands.add_parser(
        "workspace-extract-logical",
        help="Extract linear LP partitions from Stock/super.img into Logical and Work",
    )
    extract.add_argument("--project", required=True)
    extract.add_argument("--profile", required=True)
    extract.add_argument("--super-name", default="super.img")
    extract.add_argument("--no-copy-to-work", action="store_true")
    extract.add_argument("--overwrite", action="store_true")
    return parser


def _run_workspace() -> None:
    args = _workspace_parser().parse_args()
    try:
        if args.command == "workspace-create":
            manifest = create_workspace(
                Path(args.source),
                Path(args.project),
                name=args.name,
                copy_to_work=args.copy_to_work,
            )
            print(manifest.to_json())
            return
        if args.command == "workspace-info":
            print(load_workspace(Path(args.project)).to_json())
            return
        if args.command == "workspace-extract-logical":
            report = extract_logical_partitions(
                Path(args.project),
                Path(args.profile),
                super_name=args.super_name,
                copy_to_work=not args.no_copy_to_work,
                overwrite=args.overwrite,
            )
            print(report.to_json())
            return
        report = verify_workspace(Path(args.project))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report["ready"] else 2)
    except (WorkspaceError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"Orbis workspace error: {error}") from error


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "--version":
        print(f"orbis {package_version()}")
        return

    if len(sys.argv) >= 2 and sys.argv[1] in PUBLIC_WORKSPACE_COMMANDS:
        _run_workspace()
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
