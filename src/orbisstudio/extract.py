from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .gpt import parse_gpt


class ExtractionError(RuntimeError):
    """Raised when a physical-image extraction cannot be completed safely."""


@dataclass(frozen=True)
class ExtractedPartition:
    name: str
    offset: int
    size: int
    output: str
    sha256: str


@dataclass(frozen=True)
class ExtractionManifest:
    source_image: str
    source_size: int
    sector_size: int
    output_directory: str
    partitions: tuple[ExtractedPartition, ...]

    def to_json(self) -> str:
        payload = asdict(self)
        payload["partitions"] = [asdict(item) for item in self.partitions]
        return json.dumps(payload, ensure_ascii=False, indent=2)


def _safe_filename(name: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "._-" else "_" for character in name)
    cleaned = cleaned.strip("._")
    if not cleaned:
        raise ExtractionError("GPT partition has an empty or unsafe name")
    return cleaned


def _copy_range(source: Path, output: Path, offset: int, size: int, chunk_size: int) -> str:
    digest = hashlib.sha256()
    remaining = size
    temp = output.with_name(output.name + ".orbis.tmp")
    temp.unlink(missing_ok=True)
    try:
        with source.open("rb") as input_stream, temp.open("wb") as output_stream:
            input_stream.seek(offset)
            while remaining:
                block = input_stream.read(min(chunk_size, remaining))
                if not block:
                    raise ExtractionError(
                        f"Unexpected end of source image while extracting {output.name}"
                    )
                output_stream.write(block)
                digest.update(block)
                remaining -= len(block)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        if temp.stat().st_size != size:
            raise ExtractionError(
                f"Extracted size mismatch for {output.name}: expected {size}, got {temp.stat().st_size}"
            )
        os.replace(temp, output)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return digest.hexdigest()


def extract_partitions(
    image: Path,
    output_directory: Path,
    names: Iterable[str] | None = None,
    sector_size: int = 512,
    overwrite: bool = False,
    chunk_size: int = 8 * 1024 * 1024,
    manifest_path: Path | None = None,
) -> ExtractionManifest:
    image = image.expanduser().resolve()
    output_directory = output_directory.expanduser().resolve()
    if not image.is_file():
        raise ExtractionError(f"Physical image does not exist: {image}")
    if chunk_size <= 0:
        raise ExtractionError("chunk_size must be greater than zero")

    _header, partitions = parse_gpt(image, sector_size=sector_size)
    requested = set(names or ())
    known = {partition.name for partition in partitions}
    missing = sorted(requested - known)
    if missing:
        raise ExtractionError(f"Requested GPT partitions were not found: {', '.join(missing)}")

    selected = [partition for partition in partitions if not requested or partition.name in requested]
    if not selected:
        raise ExtractionError("No GPT partitions selected for extraction")

    source_size = image.stat().st_size
    for partition in selected:
        if partition.offset < 0 or partition.size <= 0:
            raise ExtractionError(f"Invalid GPT range for partition {partition.name}")
        if partition.offset + partition.size > source_size:
            raise ExtractionError(
                f"Partition {partition.name} extends beyond the physical image boundary"
            )

    output_directory.mkdir(parents=True, exist_ok=True)
    filenames: set[str] = set()
    targets: list[tuple[object, Path]] = []
    for partition in selected:
        filename = _safe_filename(partition.name) + ".img"
        folded = filename.casefold()
        if folded in filenames:
            raise ExtractionError(f"Partition filenames collide after sanitization: {filename}")
        filenames.add(folded)
        output = output_directory / filename
        if output.exists() and not overwrite:
            raise ExtractionError(f"Output already exists (use overwrite): {output}")
        targets.append((partition, output))

    extracted: list[ExtractedPartition] = []
    for partition, output in targets:
        digest = _copy_range(image, output, partition.offset, partition.size, chunk_size)
        extracted.append(
            ExtractedPartition(
                name=partition.name,
                offset=partition.offset,
                size=partition.size,
                output=str(output),
                sha256=digest,
            )
        )

    manifest = ExtractionManifest(
        source_image=str(image),
        source_size=source_size,
        sector_size=sector_size,
        output_directory=str(output_directory),
        partitions=tuple(extracted),
    )
    if manifest_path is not None:
        manifest_path = manifest_path.expanduser().resolve()
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(manifest.to_json() + "\n", encoding="utf-8")
    return manifest
