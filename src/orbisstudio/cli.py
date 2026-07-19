from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .diff import compare_trees
from .ext4 import DebugfsEditor, Ext4Error
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


def _editor(args: argparse.Namespace) -> DebugfsEditor:
    return DebugfsEditor(Path(args.debugfs) if args.debugfs else None)


def command_ext4_inspect(args: argparse.Namespace) -> int:
    print(_editor(args).inspect(Path(args.image)))
    return 0


def command_ext4_extract(args: argparse.Namespace) -> int:
    output = _editor(args).extract(Path(args.image), args.source, Path(args.output))
    print(json.dumps({"output": str(output)}, ensure_ascii=False, indent=2))
    return 0


def _parse_replacement(value: str) -> tuple[Path, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Replacement must use LOCAL_FILE=/absolute/path/in/image")
    source, destination = value.split("=", 1)
    if not source or not destination:
        raise argparse.ArgumentTypeError("Replacement must include source and destination")
    return Path(source), destination


def command_ext4_build(args: argparse.Namespace) -> int:
    replacements = [_parse_replacement(value) for value in args.replace]
    manifest = _editor(args).build(
        source_image=Path(args.image),
        output_image=Path(args.output),
        replacements=replacements,
        removals=args.remove,
        manifest_path=Path(args.manifest) if args.manifest else None,
    )
    print(manifest.to_json())
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

    ext4_inspect = commands.add_parser("ext4-inspect", help="Validate and inspect an EXT4 image")
    ext4_inspect.add_argument("--image", required=True)
    ext4_inspect.add_argument("--debugfs")
    ext4_inspect.set_defaults(handler=command_ext4_inspect)

    ext4_extract = commands.add_parser("ext4-extract", help="Extract one file from an EXT4 image")
    ext4_extract.add_argument("--image", required=True)
    ext4_extract.add_argument("--source", required=True)
    ext4_extract.add_argument("--output", required=True)
    ext4_extract.add_argument("--debugfs")
    ext4_extract.set_defaults(handler=command_ext4_extract)

    ext4_build = commands.add_parser("ext4-build", help="Create and verify an edited EXT4 image copy")
    ext4_build.add_argument("--image", required=True, help="Untouched source EXT4 image")
    ext4_build.add_argument("--output", required=True, help="New edited EXT4 image")
    ext4_build.add_argument(
        "--replace",
        action="append",
        default=[],
        metavar="LOCAL=DESTINATION",
        help="Replace a file; may be repeated",
    )
    ext4_build.add_argument(
        "--remove",
        action="append",
        default=[],
        metavar="DESTINATION",
        help="Remove a file; may be repeated",
    )
    ext4_build.add_argument("--manifest", help="Write a JSON build manifest")
    ext4_build.add_argument("--debugfs", help="Path to debugfs.exe/debugfs")
    ext4_build.set_defaults(handler=command_ext4_build)
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        raise SystemExit(args.handler(args))
    except Ext4Error as error:
        raise SystemExit(f"EXT4 error: {error}") from error
