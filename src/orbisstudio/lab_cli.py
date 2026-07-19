from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .android_config import parse_file_contexts, parse_fstab
from .ota_diff import build_delta_manifest
from .package import build_package
from .properties import edit_properties
from .selinux_audit import audit_tree
from .super_tools import unpack_super


def _key_value(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Expected KEY=VALUE")
    key, item = value.split("=", 1)
    if not key:
        raise argparse.ArgumentTypeError("Property key cannot be empty")
    return key, item


def main() -> None:
    parser = argparse.ArgumentParser(prog="orbis-lab")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("super-unpack")
    p.add_argument("--image", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--lpunpack")

    p = commands.add_parser("prop-edit")
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--set", action="append", default=[], type=_key_value)
    p.add_argument("--remove", action="append", default=[])

    p = commands.add_parser("fstab-parse")
    p.add_argument("--file", required=True)

    p = commands.add_parser("contexts-parse")
    p.add_argument("--file", required=True)

    p = commands.add_parser("contexts-audit")
    p.add_argument("--root", required=True)
    p.add_argument("--contexts", required=True)
    p.add_argument("--prefix", default="")

    p = commands.add_parser("ota-diff")
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)
    p.add_argument("--output")

    p = commands.add_parser("package")
    p.add_argument("--root", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--include", action="append", default=[])

    args = parser.parse_args()
    if args.command == "super-unpack":
        result = unpack_super(
            Path(args.image),
            Path(args.output),
            Path(args.lpunpack) if args.lpunpack else None,
        ).to_json()
    elif args.command == "prop-edit":
        result = json.dumps(
            [
                asdict(change)
                for change in edit_properties(
                    Path(args.source),
                    Path(args.output),
                    dict(args.set),
                    args.remove,
                )
            ],
            ensure_ascii=False,
            indent=2,
        )
    elif args.command == "fstab-parse":
        result = json.dumps(
            [asdict(entry) for entry in parse_fstab(Path(args.file))],
            ensure_ascii=False,
            indent=2,
        )
    elif args.command == "contexts-parse":
        result = json.dumps(
            [asdict(entry) for entry in parse_file_contexts(Path(args.file))],
            ensure_ascii=False,
            indent=2,
        )
    elif args.command == "contexts-audit":
        rules = parse_file_contexts(Path(args.contexts))
        result = audit_tree(Path(args.root), rules, args.prefix).to_json()
    elif args.command == "ota-diff":
        result = build_delta_manifest(Path(args.old), Path(args.new)).to_json()
        if args.output:
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(result + "\n", encoding="utf-8")
    else:
        result = build_package(
            Path(args.root),
            Path(args.output),
            tuple(args.include),
        ).to_json()
    print(result)


if __name__ == "__main__":
    main()
