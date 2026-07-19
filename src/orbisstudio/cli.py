from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .diff import compare_trees
from .gpt import parse_gpt
from .models import ProjectLayout
from .super_builder import build_super


def command_init(args: argparse.Namespace) -> int:
    layout = ProjectLayout.create(Path(args.project))
    print(json.dumps({key: str(value) for key, value in asdict(layout).items()}, indent=2))
    return 0


def command_inspect_gpt(args: argparse.Namespace) -> int:
    header, partitions = parse_gpt(Path(args.image), sector_size=args.sector_size)
    payload = {
        "header": asdict(header),
        "partitions": [asdict(partition) for partition in partitions],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0


def command_diff(args: argparse.Namespace) -> int:
    root = Path(args.project)
    report: dict[str, object] = {}
    for partition in ("system_a", "vendor_a", "product_a"):
        stock = root / "Stock" / partition
        work = root / "Work" / partition
        if stock.is_dir() and work.is_dir():
            report[partition] = asdict(compare_trees(stock, work))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def command_build_super(args: argparse.Namespace) -> int:
    logical = Path(args.logical)
    logical_images = {
        name: logical / f"{name}.img"
        for name in ("system_a", "vendor_a", "product_a")
        if (logical / f"{name}.img").is_file()
    }
    manifest = build_super(
        original_super=Path(args.original_super),
        logical_images=logical_images,
        profile_path=Path(args.profile),
        output=Path(args.output),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="orbis", description="OrbisStudio firmware lab")
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create a permanent project layout")
    init.add_argument("--project", required=True)
    init.set_defaults(handler=command_init)

    inspect = commands.add_parser("inspect-gpt", help="Parse and validate a GPT image")
    inspect.add_argument("--image", required=True)
    inspect.add_argument("--sector-size", type=int, default=512)
    inspect.add_argument("--output")
    inspect.set_defaults(handler=command_inspect_gpt)

    diff = commands.add_parser("diff", help="Compare Stock and Work trees")
    diff.add_argument("--project", required=True)
    diff.set_defaults(handler=command_diff)

    super_cmd = commands.add_parser("build-super", help="Inject logical images into a copy of super.img")
    super_cmd.add_argument("--original-super", required=True)
    super_cmd.add_argument("--logical", required=True)
    super_cmd.add_argument("--profile", required=True)
    super_cmd.add_argument("--output", required=True)
    super_cmd.set_defaults(handler=command_build_super)
    return root


def main() -> None:
    args = parser().parse_args()
    raise SystemExit(args.handler(args))
