from __future__ import annotations

import base64
from pathlib import Path

from orbisstudio.bootstrap import MANAGED_TOOLS, doctor, setup_tools
from orbisstudio.toolchain import find_tool


def test_setup_installs_managed_scripts_and_lockfile(tmp_path: Path) -> None:
    payloads = {
        tool.url: base64.b64encode(f"#!/usr/bin/env python3\n# {tool.name}\n".encode())
        for tool in MANAGED_TOOLS
    }

    report = setup_tools(tmp_path, downloader=lambda url: payloads[url])

    for tool in MANAGED_TOOLS:
        assert (tmp_path / tool.filename).is_file()
        launcher = tmp_path / (f"{tool.name}.cmd" if __import__("os").name == "nt" else tool.name)
        assert launcher.is_file()
        assert find_tool(tool.name, tmp_path) is not None
    assert (tmp_path / "toolchain.lock.json").is_file()
    assert {item.name for item in report.items}.issuperset({tool.name for tool in MANAGED_TOOLS})


def test_doctor_reports_missing_tools_without_crashing(tmp_path: Path) -> None:
    report = doctor(tmp_path)
    assert report.tools_directory == str(tmp_path.resolve())
    assert any(item.status == "missing" for item in report.items)
