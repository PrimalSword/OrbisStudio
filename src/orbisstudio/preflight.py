from __future__ import annotations

import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .ext4 import sha256_file

ANDROID_SPARSE_MAGIC = 0xED26FF3A
EXT4_MAGIC = 0xEF53
REQUIRED_LOGICAL = ("system_a", "vendor_a", "product_a")


class PreflightError(RuntimeError):
    """Raised when a preflight scan cannot be completed safely."""


@dataclass(frozen=True)
class ImageProbe:
    name: str
    path: str
    exists: bool
    size: int | None
    sha256: str | None
    image_type: str
    detail: str | None = None


@dataclass(frozen=True)
class PreflightReport:
    project: str
    logical_root: str
    physical_root: str | None
    ready: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    logical_images: tuple[ImageProbe, ...]
    physical_images: tuple[ImageProbe, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def _read_exact(path: Path, offset: int, size: int) -> bytes:
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(size)
    if len(data) != size:
        raise PreflightError(f"Unable to read {size} bytes at offset {offset} from {path}")
    return data


def _detect_image_type(path: Path) -> tuple[str, str | None]:
    if path.stat().st_size < 4:
        return "unknown", "file is smaller than four bytes"

    magic = struct.unpack("<I", _read_exact(path, 0, 4))[0]
    if magic == ANDROID_SPARSE_MAGIC:
        if path.stat().st_size < 28:
            return "android-sparse", "truncated sparse header"
        header = struct.unpack("<I4H4I", _read_exact(path, 0, 28))
        _, major, minor, file_hdr_sz, chunk_hdr_sz, block_size, total_blocks, total_chunks, checksum = header
        detail = (
            f"v{major}.{minor}, block={block_size}, blocks={total_blocks}, "
            f"chunks={total_chunks}, file_header={file_hdr_sz}, chunk_header={chunk_hdr_sz}, "
            f"checksum=0x{checksum:08x}"
        )
        return "android-sparse", detail

    # EXT4 stores its superblock at byte 1024 and the magic at offset 0x38.
    if path.stat().st_size >= 1082:
        ext4_magic = struct.unpack("<H", _read_exact(path, 1024 + 0x38, 2))[0]
        if ext4_magic == EXT4_MAGIC:
            log_block_size = struct.unpack("<I", _read_exact(path, 1024 + 0x18, 4))[0]
            blocks_lo = struct.unpack("<I", _read_exact(path, 1024 + 0x04, 4))[0]
            block_size = 1024 << log_block_size
            return "ext4", f"block={block_size}, blocks_lo={blocks_lo}"

    if path.name.lower().startswith("super"):
        return "super", None
    if path.name.lower().startswith("vbmeta"):
        return "vbmeta", None
    return "raw", None


def probe_image(path: Path, name: str | None = None) -> ImageProbe:
    path = path.expanduser().resolve()
    label = name or path.stem
    if not path.is_file():
        return ImageProbe(label, str(path), False, None, None, "missing")
    image_type, detail = _detect_image_type(path)
    return ImageProbe(
        name=label,
        path=str(path),
        exists=True,
        size=path.stat().st_size,
        sha256=sha256_file(path),
        image_type=image_type,
        detail=detail,
    )


def _discover_images(root: Path) -> tuple[ImageProbe, ...]:
    if not root.exists():
        return ()
    if not root.is_dir():
        raise PreflightError(f"Image root is not a directory: {root}")
    return tuple(probe_image(path) for path in sorted(root.glob("*.img")))


def _logical_probes(logical_root: Path, required: Iterable[str]) -> tuple[ImageProbe, ...]:
    return tuple(probe_image(logical_root / f"{name}.img", name) for name in required)


def run_preflight(
    project: Path,
    logical_root: Path,
    physical_root: Path | None = None,
    required_logical: Iterable[str] = REQUIRED_LOGICAL,
) -> PreflightReport:
    project = project.expanduser().resolve()
    logical_root = logical_root.expanduser().resolve()
    physical_root = physical_root.expanduser().resolve() if physical_root else None

    errors: list[str] = []
    warnings: list[str] = []

    for directory in ("Stock", "Work", "Build", "Reports"):
        candidate = project / directory
        if not candidate.is_dir():
            errors.append(f"Missing project directory: {candidate}")

    logical = _logical_probes(logical_root, required_logical)
    for image in logical:
        if not image.exists:
            errors.append(f"Missing required logical image: {image.name}.img")
            continue
        if image.size == 0:
            errors.append(f"Logical image is empty: {image.path}")
        if image.image_type not in {"ext4", "android-sparse"}:
            warnings.append(
                f"Logical image {image.name} was detected as {image.image_type}; "
                "verify that this is expected before rebuilding super.img"
            )

    physical = _discover_images(physical_root) if physical_root else ()
    if physical_root is not None:
        if not physical_root.is_dir():
            errors.append(f"Physical image directory does not exist: {physical_root}")
        else:
            names = {image.name.lower() for image in physical}
            if not any(name.startswith("super") for name in names):
                warnings.append("No super*.img image was found in the physical image directory")
            if not any(name.startswith("vbmeta") for name in names):
                warnings.append("No vbmeta*.img image was found in the physical image directory")

    hashes = [image.sha256 for image in (*logical, *physical) if image.sha256]
    if len(hashes) != len(set(hashes)):
        warnings.append("Two or more scanned images are byte-identical")

    return PreflightReport(
        project=str(project),
        logical_root=str(logical_root),
        physical_root=str(physical_root) if physical_root else None,
        ready=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        logical_images=logical,
        physical_images=physical,
    )
