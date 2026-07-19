from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dt_images import decompile_dtb, inspect_device_tree, unpack_dtbo
from .firmware_validate import validate_firmware
from .ota_payload import generate_payload
from .toolchain import toolchain_report
from .vendor_boot import unpack_vendor_boot


def main() -> None:
    parser = argparse.ArgumentParser(prog="orbis-advanced")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("toolchain")

    p = commands.add_parser("validate")
    p.add_argument("--root", required=True)
    p.add_argument("--required", action="append", default=[])

    p = commands.add_parser("vendor-boot-unpack")
    p.add_argument("--image", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--tool")

    p = commands.add_parser("dt-inspect")
    p.add_argument("--image", required=True)

    p = commands.add_parser("dt-decompile")
    p.add_argument("--image", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--dtc")

    p = commands.add_parser("dtbo-unpack")
    p.add_argument("--image", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--mkdtimg")

    p = commands.add_parser("ota-generate")
    p.add_argument("--target", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--source")
    p.add_argument("--generator")

    args = parser.parse_args()
    if args.command == "toolchain":
        result = json.dumps(toolchain_report(), ensure_ascii=False, indent=2)
    elif args.command == "validate":
        required = tuple(args.required) or ("boot", "super", "vbmeta")
        report = validate_firmware(Path(args.root), required)
        result = report.to_json()
        if not report.ready:
            print(result)
            raise SystemExit(2)
    elif args.command == "vendor-boot-unpack":
        result = unpack_vendor_boot(Path(args.image), Path(args.output), Path(args.tool) if args.tool else None).to_json()
    elif args.command == "dt-inspect":
        result = inspect_device_tree(Path(args.image)).to_json()
    elif args.command == "dt-decompile":
        result = json.dumps({"output": str(decompile_dtb(Path(args.image), Path(args.output), Path(args.dtc) if args.dtc else None))})
    elif args.command == "dtbo-unpack":
        files = unpack_dtbo(Path(args.image), Path(args.output), Path(args.mkdtimg) if args.mkdtimg else None)
        result = json.dumps({"files": [str(path) for path in files]}, ensure_ascii=False, indent=2)
    else:
        output = generate_payload(Path(args.target), Path(args.output), Path(args.source) if args.source else None,
                                  Path(args.generator) if args.generator else None)
        result = json.dumps({"payload": str(output)}, ensure_ascii=False, indent=2)
    print(result)


if __name__ == "__main__":
    main()
