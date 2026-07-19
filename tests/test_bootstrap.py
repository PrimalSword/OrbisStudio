from __future__ import annotations

import base64
import os
from pathlib import Path

from orbisstudio.bootstrap import (
    MANAGED_TOOLS,
    doctor,
    import_native_tools,
    setup_tools,
    verify_lock,
)
from orbisstudio.toolchain import find_tool


def test_setup_installs_managed_scripts_and_lockfile(tmp_path: Path) -> None:
    payloads = {
        tool.url: base64.b64encode(f"#!/usr/bin/env python3\n# {tool.name}\n".encode())
        for tool in MANAGED_TOOLS
    }

    report = setup_tools(tmp_path, downloader=lambda url: payloads[url])

    for tool in MANAGED_TOOLS:
        assert (tmp_path / tool.filename).is_file()
        launcher = tmp_path / (f"{tool.name}.cmd" if os.name == "nt" else tool.name)
        assert launcher.is_file()
        assert find_tool(tool.name, tmp_path) is not None
    assert (tmp_path / "toolchain.lock.json").is_file()
    assert {item.name for item in report.items}.issuperset({tool.name for tool in MANAGED_TOOLS})


def test_doctor_reports_missing_tools_without_crashing(tmp_path: Path) -> None:
    report = doctor(tmp_path)
    assert report.tools_directory == str(tmp_path.resolve())
    assert any(item.status == "missing" for item in report.items)


def test_import_native_tools_copies_and_locks_files(tmp_path: Path) -> None:
    source = tmp_path / "native"
    tools = tmp_path / "tools"
    source.mkdir()
    suffix = ".exe" if os.name == "nt" else ""
    for name in ("lpunpack", "lpmake", "dtc"):
        (source / f"{name}{suffix}").write_bytes(f"binary-{name}".encode())

    report = import_native_tools(source, tools)

    assert (tools / f"lpunpack{suffix}").read_bytes() == b"binary-lpunpack"
    assert (tools / "toolchain.lock.json").is_file()
    assert any(item.name == "lpunpack" and item.available for item in doctor(tools).items)
    assert report.tools_directory == str(tools.resolve())


def test_verify_lock_detects_tampering(tmp_path: Path) -> None:
    payloads = {
        tool.url: base64.b64encode(f"#!/usr/bin/env python3\n# {tool.name}\n".encode())
        for tool in MANAGED_TOOLS
    }
    setup_tools(tmp_path, downloader=lambda url: payloads[url])
    clean = verify_lock(tmp_path)
    assert all(item.status == "present" for item in clean.items if item.name in {tool.name for tool in MANAGED_TOOLS})

    (tmp_path / MANAGED_TOOLS[0].filename).write_text("tampered", encoding="utf-8")
    changed = verify_lock(tmp_path)
    assert any(item.name == MANAGED_TOOLS[0].name and item.status == "mismatch" for item in changed.items)
