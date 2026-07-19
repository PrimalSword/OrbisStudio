from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .toolchain import resolve_tool, run_tool


class OtaPayloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class PayloadResult:
    payload: str
    properties: str | None
    metadata_signature: str | None
    payload_signature: str | None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def generate_payload(
    target_images: Path,
    output: Path,
    source_images: Path | None = None,
    generator: Path | None = None,
) -> Path:
    target_images = target_images.expanduser().resolve()
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    tool = resolve_tool("payload_generator", generator)
    command = [
        str(tool),
        "--out_file",
        str(output),
        "--partition_names",
        _partition_names(target_images),
        "--new_partitions",
        _partition_paths(target_images),
    ]
    if source_images is not None:
        source_images = source_images.expanduser().resolve()
        command += ["--old_partitions", _partition_paths(source_images)]
    run_tool(command)
    if not output.is_file() or output.stat().st_size == 0:
        raise OtaPayloadError("payload generator did not produce payload.bin")
    return output


def sign_payload(
    payload: Path,
    private_key: Path,
    output: Path,
    properties: Path,
    brillo: Path | None = None,
    signature_size: int = 256,
) -> PayloadResult:
    tool = resolve_tool("brillo_update_payload", brillo)
    payload = payload.resolve()
    private_key = private_key.resolve()
    output = output.resolve()
    properties = properties.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    properties.parent.mkdir(parents=True, exist_ok=True)
    metadata_hash = output.with_suffix(".metadata.hash")
    payload_hash = output.with_suffix(".payload.hash")
    metadata_sig = output.with_suffix(".metadata.sig")
    payload_sig = output.with_suffix(".payload.sig")
    run_tool(
        [
            str(tool),
            "hash",
            "--unsigned_payload",
            str(payload),
            "--signature_size",
            str(signature_size),
            "--metadata_hash_file",
            str(metadata_hash),
            "--payload_hash_file",
            str(payload_hash),
        ]
    )
    for digest, signature in ((metadata_hash, metadata_sig), (payload_hash, payload_sig)):
        run_tool(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private_key),
                "-pkeyopt",
                "digest:sha256",
                "-in",
                str(digest),
                "-out",
                str(signature),
            ]
        )
    run_tool(
        [
            str(tool),
            "sign",
            "--unsigned_payload",
            str(payload),
            "--payload",
            str(output),
            "--metadata_signature_file",
            str(metadata_sig),
            "--payload_signature_file",
            str(payload_sig),
        ]
    )
    run_tool(
        [
            str(tool),
            "properties",
            "--payload",
            str(output),
            "--properties_file",
            str(properties),
        ]
    )
    return PayloadResult(str(output), str(properties), str(metadata_sig), str(payload_sig))


def _images(directory: Path) -> tuple[Path, ...]:
    images = tuple(sorted(path for path in directory.glob("*.img") if path.is_file()))
    if not images:
        raise OtaPayloadError(f"no .img files found: {directory}")
    return images


def _partition_names(directory: Path) -> str:
    return ":".join(
        path.stem.removesuffix("_a").removesuffix("_b") for path in _images(directory)
    )


def _partition_paths(directory: Path) -> str:
    return ":".join(str(path) for path in _images(directory))
