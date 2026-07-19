from __future__ import annotations

import struct
from pathlib import Path

from orbisstudio.dt_images import DT_TABLE_MAGIC, FDT_MAGIC, inspect_device_tree
from orbisstudio.firmware_validate import validate_firmware


def test_inspect_dtb(tmp_path: Path) -> None:
    image = tmp_path / "board.dtb"
    image.write_bytes(struct.pack(">I", FDT_MAGIC) + b"\0" * 28)
    report = inspect_device_tree(image)
    assert report.kind == "dtb"
    assert report.entry_count is None


def test_inspect_dtbo(tmp_path: Path) -> None:
    header = bytearray(32)
    struct.pack_into(">I", header, 0, DT_TABLE_MAGIC)
    struct.pack_into(">I", header, 20, 3)
    image = tmp_path / "dtbo.img"
    image.write_bytes(header)
    report = inspect_device_tree(image)
    assert report.kind == "dtbo"
    assert report.entry_count == 3


def test_validate_firmware(tmp_path: Path) -> None:
    for name in ("boot_a.img", "super.img", "vbmeta.img"):
        (tmp_path / name).write_bytes(name.encode())
    report = validate_firmware(tmp_path)
    assert report.ready
    assert len(report.hashes) == 3


def test_validate_reports_missing(tmp_path: Path) -> None:
    (tmp_path / "boot.img").write_bytes(b"boot")
    report = validate_firmware(tmp_path)
    assert not report.ready
    assert any(issue.code == "partition_missing" for issue in report.issues)
