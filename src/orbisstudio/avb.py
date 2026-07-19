from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


class AvbError(RuntimeError):
    pass


@dataclass(frozen=True)
class AvbReport:
    image: str
    sha256: str
    avbtool: str
    info: str
    verified: bool
    verification_output: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while data := handle.read(chunk_size):
            digest.update(data)
    return digest.hexdigest()


def locate_avbtool(explicit: Path | None = None) -> Path:
    candidates: list[str] = []
    if explicit is not None:
        candidates.append(str(explicit))
    if env := os.environ.get("ORBIS_AVBTOOL"):
        candidates.append(env)
    if found := shutil.which("avbtool") or shutil.which("avbtool.py"):
        candidates.append(found)
    for candidate in candidates:
        path = Path(candidate).expanduser().resolve()
        if path.is_file():
            return path
    raise AvbError("avbtool was not found; set ORBIS_AVBTOOL or pass --avbtool")


class AvbTool:
    def __init__(self, executable: Path | None = None) -> None:
        self.executable = locate_avbtool(executable)

    def _argv(self, *args: str) -> list[str]:
        if self.executable.suffix.lower() == ".py":
            return [shutil.which("python") or "python", str(self.executable), *args]
        return [str(self.executable), *args]

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(self._argv(*args), capture_output=True, text=True, check=False)
        if check and result.returncode != 0:
            output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
            raise AvbError(f"avbtool failed ({result.returncode}):\n{output}")
        return result

    def info(self, image: Path) -> str:
        image = image.resolve()
        if not image.is_file():
            raise AvbError(f"Image does not exist: {image}")
        result = self._run("info_image", "--image", str(image))
        return "\n".join(part for part in (result.stdout, result.stderr) if part).strip()

    def verify(self, image: Path, key: Path | None = None, expected_chain_partition: list[str] | None = None) -> AvbReport:
        image = image.resolve()
        info = self.info(image)
        argv = ["verify_image", "--image", str(image)]
        if key is not None:
            argv.extend(["--key", str(key.resolve())])
        for value in expected_chain_partition or []:
            argv.extend(["--expected_chain_partition", value])
        result = self._run(*argv, check=False)
        output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        return AvbReport(str(image), sha256_file(image), str(self.executable), info, result.returncode == 0, output)

    def erase_footer(self, source: Path, output: Path) -> Path:
        source = source.resolve()
        output = output.resolve()
        if source == output:
            raise AvbError("Refusing to overwrite source image")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output)
        try:
            self._run("erase_footer", "--image", str(output))
        except Exception:
            output.unlink(missing_ok=True)
            raise
        return output

    def add_hash_footer(
        self,
        image: Path,
        partition_name: str,
        partition_size: int,
        algorithm: str = "NONE",
        key: Path | None = None,
        rollback_index: int = 0,
    ) -> None:
        if not partition_name:
            raise AvbError("Partition name cannot be empty")
        argv = [
            "add_hash_footer",
            "--image", str(image.resolve()),
            "--partition_name", partition_name,
            "--partition_size", str(partition_size),
            "--algorithm", algorithm,
            "--rollback_index", str(rollback_index),
        ]
        if key is not None:
            argv.extend(["--key", str(key.resolve())])
        self._run(*argv)
