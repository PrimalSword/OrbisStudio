from __future__ import annotations

import json
from pathlib import Path

import pytest

from orbisstudio.logical_workspace import extract_logical_partitions
from orbisstudio.workspace import WorkspaceError, create_workspace


def _profile(path: Path) -> Path:
    data = {
        "metadata_slots": [
            {
                "valid": True,
                "partitions": [
                    {
                        "name": "system_a",
                        "num_extents": 1,
                        "first_extent_index": 0,
                        "size_bytes": 4,
                    },
                    {
                        "name": "vendor_a",
                        "num_extents": 1,
                        "first_extent_index": 1,
                        "size_bytes": 3,
                    },
                ],
                "extents": [
                    {"target_type": 0, "target_data": 1},
                    {"target_type": 0, "target_data": 2},
                ],
            }
        ]
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_extract_logical_partitions_into_workspace(tmp_path: Path) -> None:
    dump = tmp_path / "dump"
    dump.mkdir()
    super_image = bytearray(2048)
    super_image[512:516] = b"SYST"
    super_image[1024:1027] = b"VEN"
    (dump / "super.img").write_bytes(super_image)

    project = tmp_path / "project"
    create_workspace(dump, project)
    report = extract_logical_partitions(project, _profile(tmp_path / "lp.json"))

    assert {artifact.name for artifact in report.artifacts} == {"system_a", "vendor_a"}
    assert (project / "Logical" / "system_a.img").read_bytes() == b"SYST"
    assert (project / "Logical" / "vendor_a.img").read_bytes() == b"VEN"
    assert (project / "Work" / "system_a.img").read_bytes() == b"SYST"
    assert (project / "Reports" / "logical-map.json").is_file()


def test_extract_refuses_to_overwrite_without_flag(tmp_path: Path) -> None:
    super_image = tmp_path / "super.img"
    payload = bytearray(1024)
    payload[512:516] = b"SYST"
    super_image.write_bytes(payload)
    project = tmp_path / "project"
    create_workspace(super_image, project)
    profile = {
        "metadata_slots": [
            {
                "valid": True,
                "partitions": [
                    {
                        "name": "system_a",
                        "num_extents": 1,
                        "first_extent_index": 0,
                        "size_bytes": 4,
                    }
                ],
                "extents": [{"target_type": 0, "target_data": 1}],
            }
        ]
    }
    profile_path = tmp_path / "lp.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    extract_logical_partitions(project, profile_path)
    with pytest.raises(WorkspaceError, match="refusing to overwrite"):
        extract_logical_partitions(project, profile_path)


def test_extract_rejects_extent_outside_super(tmp_path: Path) -> None:
    super_image = tmp_path / "super.img"
    super_image.write_bytes(bytes(600))
    project = tmp_path / "project"
    create_workspace(super_image, project)
    profile = {
        "metadata_slots": [
            {
                "valid": True,
                "partitions": [
                    {
                        "name": "system_a",
                        "num_extents": 1,
                        "first_extent_index": 0,
                        "size_bytes": 100,
                    }
                ],
                "extents": [{"target_type": 0, "target_data": 1}],
            }
        ]
    }
    profile_path = tmp_path / "lp.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    with pytest.raises(WorkspaceError, match="invalid extent"):
        extract_logical_partitions(project, profile_path)
