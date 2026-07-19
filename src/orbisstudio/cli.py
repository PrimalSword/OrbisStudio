from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .avb import AvbError, AvbTool
from .diff import compare_trees
from .ext4 import DebugfsEditor, Ext4Error
from .gpt import parse_gpt
from .models import ProjectLayout
from .pipeline import PipelineError, run_pipeline
from .preflight import PreflightError, run_preflight
from .sparse import SparseError, inspect_sparse, sparse_raw, unsparse
from .super_builder import build_super


def command_init(args: argparse.Namespace) -> int:
    layout = ProjectLayout.create(Path(args.project))
    print(json.dumps({key: str(value) for key, value in asdict(layout).items()}, indent=2))
    return 0


def command_inspect_gpt(args: argparse.Namespace) -> int:
    header, partitions = parse_gpt(Path(args.image), sector_size=args.sector_size)
    payload = {"header": asdict(header), "partitions": [asdict(p) for p in partitions]}
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


def command_preflight(args: argparse.Namespace) -> int:
    report = run_preflight(
        project=Path(args.project),
        logical_root=Path(args.logical),
        physical_root=Path(args.physical) if args.physical else None,
        required_logical=args.require,
    )
    text = report.to_json()
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.ready else 2


def command_build_super(args: argparse.Namespace) -> int:
    logical = Path(args.logical)
    images = {
        name: logical / f"{name}.img"
        for name in ("system_a", "vendor_a", "product_a")
        if (logical / f"{name}.img").is_file()
    }
    manifest = build_super(
        Path(args.original_super), images, Path(args.profile), Path(args.output)
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
    print(json.dumps({"output": str(output)}, indent=2))
    return 0


def _parse_replacement(value: str) -> tuple[Path, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Replacement must use LOCAL_FILE=/absolute/path/in/image")
    source, destination = value.split("=", 1)
    if not source or not destination:
        raise argparse.ArgumentTypeError("Replacement must include source and destination")
    return Path(source), destination


def command_ext4_build(args: argparse.Namespace) -> int:
    manifest = _editor(args).build(
        Path(args.image),
        Path(args.output),
        [_parse_replacement(v) for v in args.replace],
        args.remove,
        Path(args.manifest) if args.manifest else None,
    )
    print(manifest.to_json())
    return 0


def command_sparse_inspect(args: argparse.Namespace) -> int:
    header, chunks = inspect_sparse(Path(args.image))
    print(json.dumps({"header": asdict(header), "chunks": [asdict(c) for c in chunks]}, indent=2))
    return 0


def command_unsparse(args: argparse.Namespace) -> int:
    print(json.dumps(unsparse(Path(args.image), Path(args.output)).as_dict(), indent=2))
    return 0


def command_sparse(args: argparse.Namespace) -> int:
    report = sparse_raw(
        Path(args.image), Path(args.output), args.block_size, args.max_chunk_blocks
    )
    print(json.dumps(report.as_dict(), indent=2))
    return 0


def _avb(args: argparse.Namespace) -> AvbTool:
    return AvbTool(Path(args.avbtool) if args.avbtool else None)


def command_avb_info(args: argparse.Namespace) -> int:
    print(_avb(args).info(Path(args.image)))
    return 0


def command_avb_verify(args: argparse.Namespace) -> int:
    report = _avb(args).verify(
        Path(args.image),
        Path(args.key) if args.key else None,
        args.expected_chain_partition,
    )
    print(report.to_json())
    return 0 if report.verified else 2


def command_pipeline(args: argparse.Namespace) -> int:
    result = run_pipeline(
        Path(args.plan),
        Path(args.debugfs) if args.debugfs else None,
        Path(args.avbtool) if args.avbtool else None,
    )
    print(result.to_json())
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="orbis", description="OrbisStudio firmware lab")
    commands = root.add_subparsers(dest="command", required=True)

    p = commands.add_parser("init")
    p.add_argument("--project", required=True)
    p.set_defaults(handler=command_init)

    p = commands.add_parser("inspect-gpt")
    p.add_argument("--image", required=True)
    p.add_argument("--sector-size", type=int, default=512)
    p.add_argument("--output")
    p.set_defaults(handler=command_inspect_gpt)

    p = commands.add_parser("diff")
    p.add_argument("--project", required=True)
    p.set_defaults(handler=command_diff)

    p = commands.add_parser("preflight", help="Validate project and firmware inputs before build")
    p.add_argument("--project", required=True)
    p.add_argument("--logical", required=True)
    p.add_argument("--physical")
    p.add_argument(
        "--require",
        action="append",
        default=None,
        help="Required logical partition name; may be repeated",
    )
    p.add_argument("--output", help="Write the JSON report to disk")
    p.set_defaults(handler=command_preflight)

    p = commands.add_parser("build-super")
    p.add_argument("--original-super", required=True)
    p.add_argument("--logical", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(handler=command_build_super)

    p = commands.add_parser("ext4-inspect")
    p.add_argument("--image", required=True)
    p.add_argument("--debugfs")
    p.set_defaults(handler=command_ext4_inspect)

    p = commands.add_parser("ext4-extract")
    p.add_argument("--image", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--debugfs")
    p.set_defaults(handler=command_ext4_extract)

    p = commands.add_parser("ext4-build")
    p.add_argument("--image", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--replace", action="append", default=[])
    p.add_argument("--remove", action="append", default=[])
    p.add_argument("--manifest")
    p.add_argument("--debugfs")
    p.set_defaults(handler=command_ext4_build)

    p = commands.add_parser("sparse-inspect")
    p.add_argument("--image", required=True)
    p.set_defaults(handler=command_sparse_inspect)

    p = commands.add_parser("unsparse")
    p.add_argument("--image", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(handler=command_unsparse)

    p = commands.add_parser("sparse")
    p.add_argument("--image", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--block-size", type=int, default=4096)
    p.add_argument("--max-chunk-blocks", type=int, default=1024)
    p.set_defaults(handler=command_sparse)

    p = commands.add_parser("avb-info")
    p.add_argument("--image", required=True)
    p.add_argument("--avbtool")
    p.set_defaults(handler=command_avb_info)

    p = commands.add_parser("avb-verify")
    p.add_argument("--image", required=True)
    p.add_argument("--avbtool")
    p.add_argument("--key")
    p.add_argument("--expected-chain-partition", action="append", default=[])
    p.set_defaults(handler=command_avb_verify)

    p = commands.add_parser("build", help="Run a complete JSON build plan")
    p.add_argument("--plan", required=True)
    p.add_argument("--debugfs")
    p.add_argument("--avbtool")
    p.set_defaults(handler=command_pipeline)
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "preflight" and args.require is None:
            args.require = ["system_a", "vendor_a", "product_a"]
        raise SystemExit(args.handler(args))
    except (Ext4Error, SparseError, AvbError, PipelineError, PreflightError) as error:
        raise SystemExit(f"Orbis error: {error}") from error
