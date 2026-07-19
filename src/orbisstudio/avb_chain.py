from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .toolchain import resolve_tool, run_tool


class AvbChainError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChainPartition:
    name: str
    rollback_index_location: int
    public_key: Path


@dataclass(frozen=True)
class AvbChainResult:
    output: str
    command: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str)


def make_vbmeta(
    output: Path,
    descriptors_from_images: tuple[Path, ...],
    chains: tuple[ChainPartition, ...] = (),
    key: Path | None = None,
    algorithm: str = "NONE",
    rollback_index: int = 0,
    flags: int = 0,
    avbtool: Path | None = None,
) -> AvbChainResult:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    tool = resolve_tool("avbtool", avbtool)
    command = [
        str(tool),
        "make_vbmeta_image",
        "--output",
        str(output),
        "--algorithm",
        algorithm,
        "--rollback_index",
        str(rollback_index),
        "--flags",
        str(flags),
    ]
    if key is not None:
        command += ["--key", str(key.expanduser().resolve())]
    elif algorithm != "NONE":
        raise AvbChainError("a signing key is required when algorithm is not NONE")
    for image in descriptors_from_images:
        command += ["--include_descriptors_from_image", str(image.expanduser().resolve())]
    for chain in chains:
        if not chain.public_key.is_file():
            raise AvbChainError(f"public key does not exist: {chain.public_key}")
        command += [
            "--chain_partition",
            f"{chain.name}:{chain.rollback_index_location}:{chain.public_key.resolve()}",
        ]
    run_tool(command)
    if not output.is_file() or output.stat().st_size == 0:
        raise AvbChainError("avbtool did not produce vbmeta image")
    return AvbChainResult(str(output), tuple(command))


def add_hash_footer(
    image: Path,
    partition_name: str,
    partition_size: int,
    key: Path,
    algorithm: str,
    rollback_index: int = 0,
    avbtool: Path | None = None,
) -> None:
    tool = resolve_tool("avbtool", avbtool)
    run_tool(
        [
            str(tool),
            "add_hash_footer",
            "--image",
            str(image.resolve()),
            "--partition_name",
            partition_name,
            "--partition_size",
            str(partition_size),
            "--key",
            str(key.resolve()),
            "--algorithm",
            algorithm,
            "--rollback_index",
            str(rollback_index),
        ]
    )
