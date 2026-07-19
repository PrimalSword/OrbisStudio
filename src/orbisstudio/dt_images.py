from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path

from .toolchain import resolve_tool, run_tool

FDT_MAGIC = 0xD00DFEED
DT_TABLE_MAGIC = 0xD7B7AB1E


class DeviceTreeError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeviceTreeReport:
    image: str
    kind: str
    size: int
    sha256: str
    entry_count: int | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def inspect_device_tree(image: Path) -> DeviceTreeReport:
    image = image.expanduser().resolve()
    if not image.is_file():
        raise DeviceTreeError(f"image does not exist: {image}")
    data = image.read_bytes()
    if len(data) < 4:
        raise DeviceTreeError("device-tree image is too small")
    magic = struct.unpack_from(">I", data, 0)[0]
    count = None
    if magic == FDT_MAGIC:
        kind = "dtb"
    elif magic == DT_TABLE_MAGIC:
        kind = "dtbo"
        if len(data) < 32:
            raise DeviceTreeError("truncated DTBO header")
        count = struct.unpack_from(">I", data, 20)[0]
    else:
        raise DeviceTreeError(f"unknown device-tree magic: 0x{magic:08x}")
    return DeviceTreeReport(str(image), kind, len(data), hashlib.sha256(data).hexdigest(), count)


def unpack_dtbo(image: Path, output_directory: Path, mkdtimg: Path | None = None) -> tuple[Path, ...]:
    output_directory = output_directory.expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    tool = resolve_tool("mkdtimg", mkdtimg)
    run_tool([str(tool), "dump", str(image.expanduser().resolve()), "-b", str(output_directory / "dtbo")])
    return tuple(sorted(output_directory.glob("dtbo.*")))


def decompile_dtb(image: Path, output: Path, dtc: Path | None = None) -> Path:
    output = output.expanduser().resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    tool = resolve_tool("dtc", dtc)
    run_tool([str(tool), "-I", "dtb", "-O", "dts", "-o", str(output), str(image.expanduser().resolve())])
    return output
