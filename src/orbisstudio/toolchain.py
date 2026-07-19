from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


class ToolchainError(RuntimeError):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    path: str | None
    available: bool


DEFAULT_TOOLS = (
    "lpunpack",
    "lpmake",
    "avbtool",
    "mkbootimg",
    "unpack_bootimg",
    "payload_generator",
    "brillo_update_payload",
    "dtc",
    "mkdtimg",
)


def _candidate_names(name: str) -> tuple[str, ...]:
    if os.name == "nt":
        return (name, f"{name}.exe", f"{name}.cmd", f"{name}.bat", f"{name}.py")
    return (name, f"{name}.py")


def managed_tools_directory() -> Path:
    configured = os.environ.get("ORBIS_TOOLS")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".orbisstudio" / "tools").resolve()


def find_tool(name: str, managed_directory: Path | None = None) -> Path | None:
    root = (managed_directory or managed_tools_directory()).expanduser().resolve()
    for candidate in _candidate_names(name):
        path = root / candidate
        if path.is_file():
            return path
    found = shutil.which(name)
    return Path(found).resolve() if found else None


def resolve_tool(name: str, explicit: Path | None = None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            raise ToolchainError(f"tool does not exist: {path}")
        return path
    found = find_tool(name)
    if found is None:
        raise ToolchainError(
            f"required tool not found: {name}; run 'orbis setup' or configure ORBIS_TOOLS"
        )
    return found


def inspect_toolchain(
    names: tuple[str, ...] = DEFAULT_TOOLS,
    managed_directory: Path | None = None,
) -> tuple[Tool, ...]:
    result: list[Tool] = []
    for name in names:
        path = find_tool(name, managed_directory)
        result.append(Tool(name, str(path) if path else None, path is not None))
    return tuple(result)


def run_tool(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode:
        raise ToolchainError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{result.stderr.strip()}"
        )
    return result


def toolchain_report() -> list[dict[str, object]]:
    return [asdict(item) for item in inspect_toolchain()]
