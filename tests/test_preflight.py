from __future__ import annotations

import struct
from pathlib import Path

from orbisstudio.preflight import ANDROID_SPARSE_MAGIC, probe_image, run_preflight


def _project(root: Path) -> Path:
    for name in ("Stock", "Work", "Build", "Reports"):
        (root / name).mkdir(parents=True)
    return root


def _ext4(path: Path, size: int = 8192) -> None:
    data = bytearray(size)
    struct.pack_into("<I", data, 1024 + 0x04, 2)
    struct.pack_into("<I", data, 1024 + 0x18, 2)
    struct.pack_into("<H", data, 1024 + 0x38, 0xEF53)
    path.write_bytes(data)


def _sparse(path: Path) -> None:
    header = struct.pack(
        "<I4H4I",
        ANDROID_SPARSE_MAGIC,
        1,
        0,
        28,
        12,
        4096,
        1,
        0,
        0,
    )
    path.write_bytes(header)


def test_probe_detects_ext4(tmp_path: Path) -> None:
    image = tmp_path / "system_a.img"
    _ext4(image)
    probe = probe_image(image)
    assert probe.exists is True
    assert probe.image_type == "ext4"
    assert probe.size == 8192
    assert probe.sha256 is not None
    assert "block=4096" in (probe.detail or "")


def test_probe_detects_android_sparse(tmp_path: Path) -> None:
    image = tmp_path / "vendor_a.img"
    _sparse(image)
    probe = probe_image(image)
    assert probe.image_type == "android-sparse"
    assert "chunks=0" in (probe.detail or "")


def test_preflight_ready_with_required_images(tmp_path: Path) -> None:
    project = _project(tmp_path / "Room")
    logical = tmp_path / "Logical"
    logical.mkdir()
    for name in ("system_a", "vendor_a", "product_a"):
        _ext4(logical / f"{name}.img")

    report = run_preflight(project, logical)
    assert report.ready is True
    assert report.errors == ()
    assert len(report.logical_images) == 3


def test_preflight_reports_missing_inputs(tmp_path: Path) -> None:
    project = tmp_path / "Room"
    logical = tmp_path / "Logical"
    logical.mkdir()

    report = run_preflight(project, logical)
    assert report.ready is False
    assert any("Missing project directory" in error for error in report.errors)
    assert any("Missing required logical image: system_a.img" == error for error in report.errors)


def test_preflight_discovers_super_and_vbmeta(tmp_path: Path) -> None:
    project = _project(tmp_path / "Room")
    logical = tmp_path / "Logical"
    physical = tmp_path / "Physical"
    logical.mkdir()
    physical.mkdir()
    for name in ("system_a", "vendor_a", "product_a"):
        _ext4(logical / f"{name}.img")
    (physical / "super.img").write_bytes(b"super payload")
    (physical / "vbmeta.img").write_bytes(b"vbmeta payload")

    report = run_preflight(project, logical, physical)
    assert report.ready is True
    assert not any("No super" in warning for warning in report.warnings)
    assert not any("No vbmeta" in warning for warning in report.warnings)
    assert {image.image_type for image in report.physical_images} == {"super", "vbmeta"}
