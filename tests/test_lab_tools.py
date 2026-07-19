from pathlib import Path
import json
import zipfile

from orbisstudio.android_config import parse_file_contexts, parse_fstab, resolve_context
from orbisstudio.ota_diff import build_delta_manifest
from orbisstudio.package import build_package
from orbisstudio.properties import edit_properties, read_properties
from orbisstudio.selinux_audit import audit_tree


def test_property_editor_preserves_comments_and_updates(tmp_path: Path) -> None:
    source = tmp_path / "build.prop"
    source.write_text("# header\nro.a=1\nro.b=2\n", encoding="utf-8")
    output = tmp_path / "out.prop"
    changes = edit_properties(source, output, {"ro.a": "9", "ro.c": "3"}, ["ro.b"])
    assert output.read_text(encoding="utf-8") == "# header\nro.a=9\nro.c=3\n"
    assert read_properties(output) == {"ro.a": "9", "ro.c": "3"}
    assert {item.key for item in changes} == {"ro.a", "ro.b", "ro.c"}


def test_android_config_parsers_and_audit(tmp_path: Path) -> None:
    fstab = tmp_path / "fstab"
    fstab.write_text("/dev/block/system /system ext4 ro wait,logical\n", encoding="utf-8")
    assert parse_fstab(fstab)[0].mount_point == "/system"
    contexts = tmp_path / "file_contexts"
    contexts.write_text("/system/bin(/.*)? u:object_r:system_file:s0\n", encoding="utf-8")
    rules = parse_file_contexts(contexts)
    assert resolve_context("/system/bin/sh", rules) == "u:object_r:system_file:s0"
    root = tmp_path / "tree"; (root / "bin").mkdir(parents=True); (root / "bin" / "sh").write_text("x")
    report = audit_tree(root, rules, "system")
    assert report.clean


def test_delta_manifest_and_package_are_deterministic(tmp_path: Path) -> None:
    old = tmp_path / "old"; new = tmp_path / "new"; old.mkdir(); new.mkdir()
    (old / "a.txt").write_text("old"); (new / "a.txt").write_text("new"); (new / "b.txt").write_text("added")
    delta = build_delta_manifest(old, new)
    assert [(x.path, x.status) for x in delta.entries] == [("a.txt", "modified"), ("b.txt", "added")]
    package = tmp_path / "firmware.zip"
    manifest = build_package(new, package)
    assert len(manifest.entries) == 2
    with zipfile.ZipFile(package) as archive:
        assert archive.namelist() == ["a.txt", "b.txt", "orbis-manifest.json"]
        assert json.loads(archive.read("orbis-manifest.json"))["entries"][0]["path"] == "a.txt"
