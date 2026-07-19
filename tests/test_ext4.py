from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from orbisstudio.ext4 import DebugfsEditor, Ext4Error, _normalize_destination, sha256_file


def test_normalize_destination() -> None:
    assert _normalize_destination("system/app/Test.apk") == "/system/app/Test.apk"
    assert _normalize_destination("/vendor/etc/config.xml") == "/vendor/etc/config.xml"


def test_reject_parent_traversal() -> None:
    with pytest.raises(Ext4Error):
        _normalize_destination("../../outside")


def test_sha256_file(tmp_path: Path) -> None:
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"orbis")
    assert sha256_file(sample) == hashlib.sha256(b"orbis").hexdigest()


def test_refuse_source_overwrite(tmp_path: Path) -> None:
    executable = tmp_path / "debugfs"
    executable.write_text("placeholder", encoding="utf-8")
    image = tmp_path / "system.img"
    image.write_bytes(b"not-an-ext4-image")
    replacement = tmp_path / "Launcher.apk"
    replacement.write_bytes(b"apk")

    editor = DebugfsEditor(executable)
    with pytest.raises(Ext4Error, match="Refusing to overwrite"):
        editor.build(image, image, [(replacement, "/system/app/Launcher.apk")])


def test_reject_empty_change_set(tmp_path: Path) -> None:
    executable = tmp_path / "debugfs"
    executable.write_text("placeholder", encoding="utf-8")
    image = tmp_path / "system.img"
    image.write_bytes(b"not-an-ext4-image")

    editor = DebugfsEditor(executable)
    with pytest.raises(Ext4Error, match="No EXT4 changes"):
        editor.build(image, tmp_path / "output.img", [])
