from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import pytest

from orbisstudio.bootimg import BootImageError, extract_boot_components, inspect_boot_image


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _legacy_boot(path: Path, kernel: bytes, ramdisk: bytes, page_size: int = 2048) -> None:
    header = bytearray(page_size)
    header[:8] = b"ANDROID!"
    struct.pack_into("<I", header, 8, len(kernel))
    struct.pack_into("<I", header, 16, len(ramdisk))
    struct.pack_into("<I", header, 24, 0)
    struct.pack_into("<I", header, 36, page_size)
    struct.pack_into("<I", header, 40, 0)
    struct.pack_into("<I", header, 44, 0x1234)
    header[64:64 + len(b"console=ttyS0")] = b"console=ttyS0"
    payload = bytes(header)
    payload += kernel + bytes(_align(len(kernel), page_size) - len(kernel))
    payload += ramdisk + bytes(_align(len(ramdisk), page_size) - len(ramdisk))
    path.write_bytes(payload)


def _v3_boot(path: Path, kernel: bytes, ramdisk: bytes) -> None:
    header = bytearray(4096)
    header[:8] = b"ANDROID!"
    struct.pack_into("<IIII", header, 8, len(kernel), len(ramdisk), 0x55, 1580)
    struct.pack_into("<I", header, 40, 3)
    header[44:44 + len(b"androidboot.slot_suffix=_a")] = b"androidboot.slot_suffix=_a"
    payload = bytes(header)
    payload += kernel + bytes(_align(len(kernel), 4096) - len(kernel))
    payload += ramdisk + bytes(_align(len(ramdisk), 4096) - len(ramdisk))
    path.write_bytes(payload)


def test_inspect_legacy_boot_image(tmp_path: Path) -> None:
    image = tmp_path / "boot.img"
    _legacy_boot(image, b"KERNEL", b"RAMDISK")
    report = inspect_boot_image(image)
    assert report.header_version == 0
    assert report.page_size == 2048
    assert report.cmdline == "console=ttyS0"
    assert [item.name for item in report.components] == ["kernel", "ramdisk"]
    assert report.components[0].sha256 == hashlib.sha256(b"KERNEL").hexdigest()


def test_inspect_v3_boot_image(tmp_path: Path) -> None:
    image = tmp_path / "boot-v3.img"
    _v3_boot(image, b"K" * 17, b"R" * 9)
    report = inspect_boot_image(image)
    assert report.header_version == 3
    assert report.page_size == 4096
    assert report.cmdline == "androidboot.slot_suffix=_a"
    assert report.components[1].size == 9


def test_extract_components_and_manifest(tmp_path: Path) -> None:
    image = tmp_path / "boot.img"
    _legacy_boot(image, b"abc", b"defg")
    manifest = tmp_path / "manifest.json"
    report = extract_boot_components(image, tmp_path / "out", manifest_path=manifest)
    assert (tmp_path / "out" / "kernel.bin").read_bytes() == b"abc"
    assert (tmp_path / "out" / "ramdisk.bin").read_bytes() == b"defg"
    assert manifest.is_file()
    assert all(item.output for item in report.components)


def test_rejects_overwrite_by_default(tmp_path: Path) -> None:
    image = tmp_path / "boot.img"
    _legacy_boot(image, b"abc", b"def")
    output = tmp_path / "out"
    extract_boot_components(image, output)
    with pytest.raises(BootImageError, match="already exists"):
        extract_boot_components(image, output)


def test_rejects_invalid_magic(tmp_path: Path) -> None:
    image = tmp_path / "bad.img"
    image.write_bytes(bytes(4096))
    with pytest.raises(BootImageError, match="boot magic"):
        inspect_boot_image(image)


def test_rejects_component_outside_image(tmp_path: Path) -> None:
    image = tmp_path / "truncated.img"
    header = bytearray(2048)
    header[:8] = b"ANDROID!"
    struct.pack_into("<I", header, 8, 999999)
    struct.pack_into("<I", header, 36, 2048)
    struct.pack_into("<I", header, 40, 0)
    image.write_bytes(header)
    with pytest.raises(BootImageError, match="boundary"):
        inspect_boot_image(image)
