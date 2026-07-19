from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


class Ext4Error(RuntimeError):
    """Raised when an EXT4 operation cannot be completed safely."""


@dataclass(frozen=True)
class Ext4Change:
    operation: str
    source: str | None
    destination: str
    size: int | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class Ext4BuildManifest:
    source_image: str
    output_image: str
    source_sha256: str
    output_sha256: str
    backend: str
    changes: tuple[Ext4Change, ...]

    def to_json(self) -> str:
        payload = asdict(self)
        payload["changes"] = [asdict(change) for change in self.changes]
        return json.dumps(payload, ensure_ascii=False, indent=2)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_destination(path: str) -> str:
    if not path:
        raise Ext4Error("Destination path cannot be empty")
    normalized = PurePosixPath("/" + path.lstrip("/"))
    if ".." in normalized.parts:
        raise Ext4Error(f"Unsafe destination path: {path}")
    return str(normalized)


def locate_debugfs(explicit: Path | None = None) -> Path:
    candidates: list[str] = []
    if explicit is not None:
        candidates.append(str(explicit))
    env_path = os.environ.get("ORBIS_DEBUGFS")
    if env_path:
        candidates.append(env_path)
    discovered = shutil.which("debugfs") or shutil.which("debugfs.exe")
    if discovered:
        candidates.append(discovered)

    for candidate in candidates:
        path = Path(candidate).expanduser().resolve()
        if path.is_file():
            return path
    raise Ext4Error(
        "debugfs was not found. Set ORBIS_DEBUGFS to a debugfs executable or pass --debugfs."
    )


class DebugfsEditor:
    """Transactional EXT4 image editor using e2fsprogs debugfs.

    The original image is never modified. All commands are applied to a temporary copy,
    verified, and atomically moved to the requested output path only on success.
    """

    def __init__(self, debugfs: Path | None = None) -> None:
        self.debugfs = locate_debugfs(debugfs)

    def _run(self, image: Path, commands: Iterable[str], writable: bool = False) -> str:
        command_list = list(commands)
        if not command_list:
            return ""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False) as script:
            script.write("\n".join(command_list))
            script.write("\n")
            script_path = Path(script.name)
        try:
            argv = [str(self.debugfs)]
            if writable:
                argv.append("-w")
            argv.extend(["-f", str(script_path), str(image)])
            result = subprocess.run(argv, capture_output=True, text=True, check=False)
            output = "\n".join(part for part in (result.stdout, result.stderr) if part)
            fatal_markers = (
                "Filesystem not open",
                "Command not found",
                "Could not allocate",
                "No space left",
                "File not found by ext2_lookup",
                "Ext2 inode is not a directory",
            )
            if result.returncode != 0 or any(marker in output for marker in fatal_markers):
                raise Ext4Error(
                    f"debugfs failed with exit code {result.returncode}:\n{output.strip()}"
                )
            return output
        finally:
            script_path.unlink(missing_ok=True)

    def inspect(self, image: Path) -> str:
        image = image.resolve()
        if not image.is_file():
            raise Ext4Error(f"EXT4 image does not exist: {image}")
        return self._run(image, ["stats"])

    def extract(self, image: Path, source: str, output: Path) -> Path:
        source = _normalize_destination(source)
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        self._run(image.resolve(), [f'dump "{source}" "{output}"'])
        if not output.is_file():
            raise Ext4Error(f"debugfs did not extract {source}")
        return output

    def build(
        self,
        source_image: Path,
        output_image: Path,
        replacements: Iterable[tuple[Path, str]],
        removals: Iterable[str] = (),
        manifest_path: Path | None = None,
    ) -> Ext4BuildManifest:
        source_image = source_image.resolve()
        output_image = output_image.resolve()
        if not source_image.is_file():
            raise Ext4Error(f"Source image does not exist: {source_image}")
        if source_image == output_image:
            raise Ext4Error("Refusing to overwrite the source image")

        replacement_list: list[tuple[Path, str]] = []
        changes: list[Ext4Change] = []
        commands: list[str] = []

        for destination in removals:
            normalized = _normalize_destination(destination)
            commands.append(f'rm "{normalized}"')
            changes.append(Ext4Change("remove", None, normalized))

        for source, destination in replacements:
            source = source.resolve()
            if not source.is_file():
                raise Ext4Error(f"Replacement file does not exist: {source}")
            normalized = _normalize_destination(destination)
            replacement_list.append((source, normalized))
            commands.extend([f'rm "{normalized}"', f'write "{source}" "{normalized}"'])
            changes.append(
                Ext4Change(
                    operation="replace",
                    source=str(source),
                    destination=normalized,
                    size=source.stat().st_size,
                    sha256=sha256_file(source),
                )
            )

        if not commands:
            raise Ext4Error("No EXT4 changes were requested")

        output_image.parent.mkdir(parents=True, exist_ok=True)
        source_hash = sha256_file(source_image)
        temp_image = output_image.with_name(output_image.name + ".orbis.tmp")
        temp_image.unlink(missing_ok=True)
        shutil.copy2(source_image, temp_image)

        try:
            self._run(temp_image, commands, writable=True)
            self._run(temp_image, ["stats"])
            self._verify_replacements(temp_image, replacement_list)
            output_hash = sha256_file(temp_image)
            if output_hash == source_hash:
                raise Ext4Error("Output image is byte-identical to source after requested changes")
            os.replace(temp_image, output_image)
        except Exception:
            temp_image.unlink(missing_ok=True)
            raise

        manifest = Ext4BuildManifest(
            source_image=str(source_image),
            output_image=str(output_image),
            source_sha256=source_hash,
            output_sha256=output_hash,
            backend=str(self.debugfs),
            changes=tuple(changes),
        )
        if manifest_path is not None:
            manifest_path = manifest_path.resolve()
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(manifest.to_json() + "\n", encoding="utf-8")
        return manifest

    def _verify_replacements(self, image: Path, replacements: list[tuple[Path, str]]) -> None:
        if not replacements:
            return
        with tempfile.TemporaryDirectory(prefix="orbis-ext4-verify-") as directory:
            root = Path(directory)
            for index, (source, destination) in enumerate(replacements):
                extracted = root / f"{index:04d}.bin"
                self.extract(image, destination, extracted)
                expected = sha256_file(source)
                actual = sha256_file(extracted)
                if expected != actual:
                    raise Ext4Error(
                        f"Verification failed for {destination}: expected {expected}, got {actual}"
                    )
