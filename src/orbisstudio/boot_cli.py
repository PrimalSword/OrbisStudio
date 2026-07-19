from __future__ import annotations

import argparse
from pathlib import Path

from .bootimg import BootImageError, extract_boot_components, inspect_boot_image


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="orbis-boot", description="Inspect and extract Android boot images")
    commands = root.add_subparsers(dest="command", required=True)

    inspect = commands.add_parser("inspect", help="Inspect an Android boot image")
    inspect.add_argument("--image", required=True)
    inspect.add_argument("--output", help="Write JSON report to disk")

    extract = commands.add_parser("extract", help="Extract kernel and ramdisk components")
    extract.add_argument("--image", required=True)
    extract.add_argument("--output", required=True)
    extract.add_argument("--manifest")
    extract.add_argument("--overwrite", action="store_true")
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "inspect":
            report = inspect_boot_image(Path(args.image))
            text = report.to_json()
            if args.output:
                target = Path(args.output).expanduser().resolve()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text + "\n", encoding="utf-8")
            print(text)
            return

        report = extract_boot_components(
            Path(args.image),
            Path(args.output),
            overwrite=args.overwrite,
            manifest_path=Path(args.manifest) if args.manifest else None,
        )
        print(report.to_json())
    except BootImageError as error:
        raise SystemExit(f"Orbis boot error: {error}") from error


if __name__ == "__main__":
    main()
