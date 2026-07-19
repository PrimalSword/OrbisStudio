from __future__ import annotations

import argparse
from pathlib import Path

from .extract import ExtractionError, extract_partitions


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="orbis-extract",
        description="Safely extract GPT partitions from a physical firmware image",
    )
    command.add_argument("--image", required=True, help="Physical disk image such as mmcblk0.img")
    command.add_argument("--output", required=True, help="Destination directory for partition images")
    command.add_argument(
        "--partition",
        action="append",
        default=[],
        help="GPT partition name to extract; may be repeated. Extracts all when omitted.",
    )
    command.add_argument("--sector-size", type=int, default=512)
    command.add_argument("--chunk-size", type=int, default=8 * 1024 * 1024)
    command.add_argument("--overwrite", action="store_true")
    command.add_argument("--manifest", help="Optional JSON extraction manifest")
    return command


def main() -> None:
    args = parser().parse_args()
    try:
        manifest = extract_partitions(
            image=Path(args.image),
            output_directory=Path(args.output),
            names=args.partition,
            sector_size=args.sector_size,
            overwrite=args.overwrite,
            chunk_size=args.chunk_size,
            manifest_path=Path(args.manifest) if args.manifest else None,
        )
    except (ExtractionError, ValueError, OSError) as error:
        raise SystemExit(f"Orbis extraction error: {error}") from error
    print(manifest.to_json())


if __name__ == "__main__":
    main()
