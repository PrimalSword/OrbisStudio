from __future__ import annotations

import hashlib
import json
import os
import struct
from dataclasses import asdict, dataclass
from pathlib import Path


BOOT_MAGIC = b"ANDROID!"
V3_PAGE_SIZE = 4096


class BootImageError(RuntimeError):
    """Raised when an Android boot image is malformed or unsupported."""


@dataclass(frozen=True)
class BootComponent:
    name: str
    offset: int
    size: int
    sha256: str
    output: str | None = None


@dataclass(frozen=True)
class BootImageReport:
    image: str
    image_size: int
    header_version: int
    page_size: int
    os_version_raw: int
    cmdline: str
    components: tuple[BootComponent, ...]

    def to_json(self) -> str:
        payload = asdict(self)
        payload["components"] = [asdict(item) for item in self.components]
        return json.dumps(payload, ensure_ascii=False, indent=2)


def _align(value: int, alignment: int) -> int:
    if alignment <= 0:
        raise BootImageError("alignment must be greater than zero")
    return (value + alignment - 1) // alignment * alignment


def _cstring(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()


def _sha256_range(image: Path, offset: int, size: int, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    remaining = size
    with image.open("rb") as stream:
        stream.seek(offset)
        while remaining:
            block = stream.read(min(chunk_size, remaining))
            if not block:
                raise BootImageError("unexpected end of boot image")
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()


def _component(image: Path, name: str, offset: int, size: int, image_size: int) -> BootComponent:
    if size < 0 or offset < 0 or offset + size > image_size:
        raise BootImageError(f"component {name} exceeds image boundary")
    return BootComponent(name=name, offset=offset, size=size, sha256=_sha256_range(image, offset, size))


def inspect_boot_image(image: Path) -> BootImageReport:
    image = image.expanduser().resolve()
    if not image.is_file():
        raise BootImageError(f"boot image does not exist: {image}")
    image_size = image.stat().st_size
    if image_size < 48:
        raise BootImageError("boot image is too small")

    with image.open("rb") as stream:
        header = stream.read(min(image_size, 4096))

    if header[:8] != BOOT_MAGIC:
        raise BootImageError("ANDROID! boot magic not found")

    # Header v3/v4 stores header_version at byte 40 and always uses 4096-byte pages.
    possible_v3 = struct.unpack_from("<I", header, 40)[0]
    if possible_v3 in (3, 4):
        kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from("<IIII", header, 8)
        if header_size < 1580 or header_size > V3_PAGE_SIZE:
            raise BootImageError(f"invalid boot header size: {header_size}")
        cmdline = _cstring(header[44:44 + 1536])
        kernel_offset = V3_PAGE_SIZE
        ramdisk_offset = kernel_offset + _align(kernel_size, V3_PAGE_SIZE)
        components = [
            _component(image, "kernel", kernel_offset, kernel_size, image_size),
            _component(image, "ramdisk", ramdisk_offset, ramdisk_size, image_size),
        ]
        return BootImageReport(
            image=str(image), image_size=image_size, header_version=possible_v3,
            page_size=V3_PAGE_SIZE, os_version_raw=os_version, cmdline=cmdline,
            components=tuple(components),
        )

    # Legacy v0-v2 layout.
    kernel_size = struct.unpack_from("<I", header, 8)[0]
    ramdisk_size = struct.unpack_from("<I", header, 16)[0]
    second_size = struct.unpack_from("<I", header, 24)[0]
    page_size = struct.unpack_from("<I", header, 36)[0]
    header_version = struct.unpack_from("<I", header, 40)[0]
    os_version = struct.unpack_from("<I", header, 44)[0]
    if page_size < 512 or page_size & (page_size - 1):
        raise BootImageError(f"invalid legacy page size: {page_size}")
    if header_version not in (0, 1, 2):
        raise BootImageError(f"unsupported boot header version: {header_version}")

    cmdline = _cstring(header[64:64 + 512] + header[608:608 + 1024])
    kernel_offset = page_size
    ramdisk_offset = kernel_offset + _align(kernel_size, page_size)
    second_offset = ramdisk_offset + _align(ramdisk_size, page_size)
    components = [
        _component(image, "kernel", kernel_offset, kernel_size, image_size),
        _component(image, "ramdisk", ramdisk_offset, ramdisk_size, image_size),
    ]
    if second_size:
        components.append(_component(image, "second", second_offset, second_size, image_size))

    return BootImageReport(
        image=str(image), image_size=image_size, header_version=header_version,
        page_size=page_size, os_version_raw=os_version, cmdline=cmdline,
        components=tuple(components),
    )


def extract_boot_components(
    image: Path,
    output_directory: Path,
    overwrite: bool = False,
    manifest_path: Path | None = None,
) -> BootImageReport:
    report = inspect_boot_image(image)
    output_directory = output_directory.expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    source = Path(report.image)
    extracted: list[BootComponent] = []

    for component in report.components:
        target = output_directory / f"{component.name}.bin"
        if target.exists() and not overwrite:
            raise BootImageError(f"output already exists: {target}")
        temp = target.with_name(target.name + ".orbis.tmp")
        temp.unlink(missing_ok=True)
        remaining = component.size
        digest = hashlib.sha256()
        try:
            with source.open("rb") as input_stream, temp.open("wb") as output_stream:
                input_stream.seek(component.offset)
                while remaining:
                    block = input_stream.read(min(8 * 1024 * 1024, remaining))
                    if not block:
                        raise BootImageError(f"unexpected end while extracting {component.name}")
                    output_stream.write(block)
                    digest.update(block)
                    remaining -= len(block)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            if digest.hexdigest() != component.sha256:
                raise BootImageError(f"hash mismatch while extracting {component.name}")
            os.replace(temp, target)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
        extracted.append(BootComponent(component.name, component.offset, component.size, component.sha256, str(target)))

    result = BootImageReport(
        image=report.image,
        image_size=report.image_size,
        header_version=report.header_version,
        page_size=report.page_size,
        os_version_raw=report.os_version_raw,
        cmdline=report.cmdline,
        components=tuple(extracted),
    )
    if manifest_path is not None:
        manifest_path = manifest_path.expanduser().resolve()
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(result.to_json() + "\n", encoding="utf-8")
    return result
