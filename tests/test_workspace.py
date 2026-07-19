from __future__ import annotations

import json
from pathlib import Path

import pytest

from orbisstudio.workspace import WorkspaceError, create_workspace, load_workspace, verify_workspace


def test_create_workspace_copies_and_hashes_firmware(tmp_path: Path) -> None:
    source = tmp_path / "dump"
    source.mkdir()
    (source / "boot.img").write_bytes(b"boot-image")
    (source / "super.img").write_bytes(b"super-image")
    (source / "notes.txt").write_text("ignored", encoding="utf-8")

    project = tmp_path / "HY300"
    manifest = create_workspace(source, project, name="HY300 Stock", copy_to_work=True)

    assert manifest.name == "HY300 Stock"
    assert {item.name for item in manifest.artifacts} == {"boot.img", "super.img"}
    assert (project / "Stock" / "boot.img").read_bytes() == b"boot-image"
    assert (project / "Work" / "super.img").read_bytes() == b"super-image"
    assert (project / "Logical").is_dir()
    assert (project / "Output").is_dir()
    assert (project / "Reports").is_dir()
    assert (project / "Backups").is_dir()

    stored = json.loads((project / ".orbis.json").read_text(encoding="utf-8"))
    assert stored["schema_version"] == 1
    assert len(stored["artifacts"]) == 2
    assert verify_workspace(project)["ready"] is True


def test_workspace_verify_detects_stock_mutation(tmp_path: Path) -> None:
    image = tmp_path / "boot.img"
    image.write_bytes(b"original")
    project = tmp_path / "project"
    create_workspace(image, project)

    (project / "Stock" / "boot.img").write_bytes(b"changed")
    report = verify_workspace(project)

    assert report["ready"] is False
    assert report["items"][0]["status"] == "mismatch"


def test_workspace_refuses_existing_manifest(tmp_path: Path) -> None:
    image = tmp_path / "boot.img"
    image.write_bytes(b"firmware")
    project = tmp_path / "project"
    create_workspace(image, project)

    with pytest.raises(WorkspaceError, match="already exists"):
        create_workspace(image, project)


def test_load_workspace_requires_manifest(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError, match="manifest not found"):
        load_workspace(tmp_path / "missing")
