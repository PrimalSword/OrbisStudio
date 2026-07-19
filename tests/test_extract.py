from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from orbisstudio.extract import ExtractionError, extract_partitions
from orbisstudio.models import Partition


def _partition(name: str, offset: int, size: int) -> Partition:
    return Partition(
        name=name,
        offset=offset,
        size=size,
        type_guid="00000000-0000-0000-0000-000000000001",
        unique_guid="00000000-0000-0000-0000-000000000002",
        attributes=0,
    )


def test_extract_selected_partition_and_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "disk.img"
    image.write_bytes(b"HEAD" + b"SYSTEM" + b"VENDOR")
    monkeypatch.setattr(
        "orbisstudio.extract.parse_gpt",
        lambda _image, sector_size=512: (object(), [_partition("system_a", 4, 6), _partition("vendor_a", 10, 6)]),
    )

    manifest_path = tmp_path / "manifest.json"
    result = extract_partitions(
        image,
        tmp_path / "out",
        names=["vendor_a"],
        manifest_path=manifest_path,
        chunk_size=2,
    )

    output = tmp_path / "out" / "vendor_a.img"
    assert output.read_bytes() == b"VENDOR"
    assert result.partitions[0].sha256 == hashlib.sha256(b"VENDOR").hexdigest()
    assert manifest_path.is_file()
    assert "vendor_a" in manifest_path.read_text(encoding="utf-8")


def test_extract_refuses_existing_output_without_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "disk.img"
    image.write_bytes(b"12345678")
    monkeypatch.setattr(
        "orbisstudio.extract.parse_gpt",
        lambda _image, sector_size=512: (object(), [_partition("boot", 0, 4)]),
    )
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "boot.img").write_bytes(b"KEEP")

    with pytest.raises(ExtractionError, match="already exists"):
        extract_partitions(image, output_dir)

    assert (output_dir / "boot.img").read_bytes() == b"KEEP"


def test_extract_rejects_partition_beyond_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "disk.img"
    image.write_bytes(b"tiny")
    monkeypatch.setattr(
        "orbisstudio.extract.parse_gpt",
        lambda _image, sector_size=512: (object(), [_partition("broken", 2, 8)]),
    )

    with pytest.raises(ExtractionError, match="beyond"):
        extract_partitions(image, tmp_path / "out")


def test_extract_rejects_unknown_requested_partition(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "disk.img"
    image.write_bytes(b"12345678")
    monkeypatch.setattr(
        "orbisstudio.extract.parse_gpt",
        lambda _image, sector_size=512: (object(), [_partition("boot", 0, 4)]),
    )

    with pytest.raises(ExtractionError, match="not found"):
        extract_partitions(image, tmp_path / "out", names=["vbmeta"])


def test_extract_sanitizes_partition_filename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "disk.img"
    image.write_bytes(b"ABCD")
    monkeypatch.setattr(
        "orbisstudio.extract.parse_gpt",
        lambda _image, sector_size=512: (object(), [_partition("system/a", 0, 4)]),
    )

    extract_partitions(image, tmp_path / "out")
    assert (tmp_path / "out" / "system_a.img").read_bytes() == b"ABCD"
