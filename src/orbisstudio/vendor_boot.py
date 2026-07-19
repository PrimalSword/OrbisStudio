from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .toolchain import resolve_tool, run_tool


class VendorBootError(RuntimeError):
    pass


@dataclass(frozen=True)
class VendorBootResult:
    image: str
    output_directory: str
    files: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def unpack_vendor_boot(image: Path, output_directory: Path, unpack_bootimg: Path | None = None) -> VendorBootResult:
    image = image.expanduser().resolve()
    if not image.is_file():
        raise VendorBootError(f"vendor_boot image does not exist: {image}")
    output_directory = output_directory.expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    tool = resolve_tool("unpack_bootimg", unpack_bootimg)
    run_tool([str(tool), "--boot_img", str(image), "--out", str(output_directory)])
    files = tuple(str(path.relative_to(output_directory)) for path in sorted(output_directory.rglob("*")) if path.is_file())
    return VendorBootResult(str(image), str(output_directory), files)


def repack_vendor_boot(arguments: list[str], output: Path, mkbootimg: Path | None = None) -> Path:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    tool = resolve_tool("mkbootimg", mkbootimg)
    command = [str(tool), *arguments, "--vendor_boot", str(output)]
    run_tool(command)
    if not output.is_file() or output.stat().st_size == 0:
        raise VendorBootError("mkbootimg did not produce vendor_boot output")
    return output
