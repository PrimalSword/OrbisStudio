from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import json
import zipfile


@dataclass(frozen=True)
class PackageEntry:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class PackageManifest:
    output: str
    entries: tuple[PackageEntry, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def _hash(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def build_package(root: Path, output: Path, include: tuple[str, ...] = ()) -> PackageManifest:
    root = root.expanduser().resolve()
    output = output.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Package root does not exist: {root}")
    selected = []
    for item in root.rglob("*"):
        if not item.is_file() or item.resolve() == output:
            continue
        relative = item.relative_to(root).as_posix()
        if include and not any(item.match(pattern) or relative == pattern for pattern in include):
            continue
        selected.append((relative, item))
    if not selected:
        raise ValueError("No files selected for package")
    selected.sort(key=lambda pair: pair[0])
    entries = tuple(PackageEntry(name, path.stat().st_size, _hash(path)) for name, path in selected)
    manifest_text = json.dumps({"entries": [asdict(entry) for entry in entries]}, ensure_ascii=False, indent=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, path in selected:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
        info = zipfile.ZipInfo("orbis-manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, manifest_text.encode("utf-8"))
    return PackageManifest(str(output), entries)
