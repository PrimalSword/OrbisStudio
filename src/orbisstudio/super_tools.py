from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import shutil
import subprocess


class SuperToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class SuperUnpackReport:
    source: str
    output_directory: str
    images: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def unpack_super(source: Path, output_directory: Path, lpunpack: Path | None = None) -> SuperUnpackReport:
    source = source.expanduser().resolve()
    output_directory = output_directory.expanduser().resolve()
    if not source.is_file():
        raise SuperToolError(f"super image does not exist: {source}")
    executable = str(lpunpack) if lpunpack else shutil.which("lpunpack")
    if not executable:
        raise SuperToolError("lpunpack was not found; pass --lpunpack or add it to PATH")
    output_directory.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in output_directory.glob("*.img")}
    process = subprocess.run([executable, str(source), str(output_directory)], capture_output=True, text=True, check=False)
    if process.returncode != 0:
        raise SuperToolError((process.stderr or process.stdout or "lpunpack failed").strip())
    images = tuple(str(p.resolve()) for p in sorted(output_directory.glob("*.img")) if p.name not in before or p.stat().st_size > 0)
    if not images:
        raise SuperToolError("lpunpack completed without producing logical images")
    return SuperUnpackReport(str(source), str(output_directory), images)
