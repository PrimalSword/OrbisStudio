from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json

from .toolchain import ToolchainError, resolve_tool, run_tool


class SuperToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class SuperUnpackReport:
    source: str
    output_directory: str
    images: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def unpack_super(
    source: Path,
    output_directory: Path,
    lpunpack: Path | None = None,
) -> SuperUnpackReport:
    source = source.expanduser().resolve()
    output_directory = output_directory.expanduser().resolve()
    if not source.is_file():
        raise SuperToolError(f"super image does not exist: {source}")
    try:
        executable = resolve_tool("lpunpack", lpunpack)
    except ToolchainError as error:
        raise SuperToolError(str(error)) from error

    output_directory.mkdir(parents=True, exist_ok=True)
    before = {path.name for path in output_directory.glob("*.img")}
    try:
        run_tool([str(executable), str(source), str(output_directory)])
    except ToolchainError as error:
        raise SuperToolError(str(error)) from error

    images = tuple(
        str(path.resolve())
        for path in sorted(output_directory.glob("*.img"))
        if path.name not in before or path.stat().st_size > 0
    )
    if not images:
        raise SuperToolError("lpunpack completed without producing logical images")
    return SuperUnpackReport(str(source), str(output_directory), images)
