from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path


class ToolchainError(RuntimeError):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    path: str | None
    available: bool


DEFAULT_TOOLS = ("lpunpack", "lpmake", "avbtool", "mkbootimg", "unpack_bootimg", "payload_generator", "brillo_update_payload", "dtc", "mkdtimg")


def resolve_tool(name: str, explicit: Path | None = None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            raise ToolchainError(f"tool does not exist: {path}")
        return path
    found = shutil.which(name)
    if not found:
        raise ToolchainError(f"required tool not found in PATH: {name}")
    return Path(found).resolve()


def inspect_toolchain(names: tuple[str, ...] = DEFAULT_TOOLS) -> tuple[Tool, ...]:
    return tuple(Tool(name, shutil.which(name), shutil.which(name) is not None) for name in names)


def run_tool(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode:
        raise ToolchainError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stderr.strip()}")
    return result


def toolchain_report() -> list[dict[str, object]]:
    return [asdict(item) for item in inspect_toolchain()]
