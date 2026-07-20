from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import pytest

from orbisstudio.lp_metadata import LpMetadataError, inspect_lp_metadata


def _name(value: str, size: int = 36) -> bytes:
    raw = value.encode("utf-8")
    return raw + bytes(size - len(raw))


def _checked(data: bytearray, checksum_offset: int) -> bytes:
    data[checksum_offset : checksum_offset + 32] = bytes(32)
    data[checksum_offset : checksum_offset + 32] = hashlib.sha256(data).digest()
    return bytes(data)


def _super_image(path: Path, corrupt_backup: bool = False) -> None:
    metadata_max_size = 4096
    slot_count = 1
    image = bytearray(32768)

    geometry = bytearray(52)
    struct.pack_into("<II", geometry, 0, 0x616C4467, 52)
    struct.pack_into("<III", geometry, 40, metadata_max_size, slot_count, 4096)
    geometry = bytearray(_checked(geometry, 8))
    image[4096 : 4096 + 52] = geometry
    image[8192 : 8192 + 52] = geometry

    partition = _name("system_a") + struct.pack("<IIII", 0, 0, 1, 0)
    extent = struct.pack("<QIQI", 8, 0, 48, 0)
    group = _name("default") + struct.pack("<IQ", 0, 4096)
    block = struct.pack("<QIIQ", 48, 4096, 0, len(image)) + _name("super") + struct.pack("<I", 0)
    tables = partition + extent + group + block

    header = bytearray(128)
    struct.pack_into("<IHHI", header, 0, 0x414C5030, 10, 2, 128)
    struct.pack_into("<I", header, 44, len(tables))
    header[48:80] = hashlib.sha256(tables).digest()
    offset = 0
    for descriptor_offset, count, size in (
        (80, 1, 52),
        (92, 1, 24),
        (104, 1, 48),
        (116, 1, 64),
    ):
        struct.pack_into("<III", header, descriptor_offset, offset, count, size)
        offset += count * size
    header = bytearray(_checked(header, 12))

    primary = 12288
    backup = primary + metadata_max_size
    image[primary : primary + 128] = header
    image[primary + 128 : primary + 128 + len(tables)] = tables
    image[backup : backup + 128] = header
    image[backup + 128 : backup + 128 + len(tables)] = tables
    if corrupt_backup:
        image[backup + 128] ^= 0xFF
    path.write_bytes(image)


def test_inspect_lp_metadata_reads_geometry_tables_and_sizes(tmp_path: Path) -> None:
    image = tmp_path / "super.img"
    _super_image(image)

    report = inspect_lp_metadata(image)

    assert report.geometry.valid is True
    assert report.geometry.metadata_slot_count == 1
    assert len(report.metadata_slots) == 2
    slot = report.metadata_slots[0]
    assert slot.valid is True
    assert slot.major_version == 10
    assert slot.minor_version == 2
    assert slot.partitions[0]["name"] == "system_a"
    assert slot.partitions[0]["size_bytes"] == 4096
    assert slot.extents[0]["target_data"] == 48
    assert slot.groups[0]["name"] == "default"
    assert slot.block_devices[0]["partition_name"] == "super"


def test_inspect_lp_metadata_keeps_valid_primary_when_backup_is_corrupt(tmp_path: Path) -> None:
    image = tmp_path / "super.img"
    _super_image(image, corrupt_backup=True)

    report = inspect_lp_metadata(image)

    assert report.metadata_slots[0].valid is True
    assert report.metadata_slots[1].valid is False
    assert report.metadata_slots[1].error == "metadata tables checksum mismatch"


def test_inspect_lp_metadata_rejects_image_without_geometry(tmp_path: Path) -> None:
    image = tmp_path / "super.img"
    image.write_bytes(bytes(32768))

    with pytest.raises(LpMetadataError, match="no valid LP geometry"):
        inspect_lp_metadata(image)
