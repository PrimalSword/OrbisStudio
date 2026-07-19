from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import json


@dataclass(frozen=True)
class DeltaEntry:
    path: str
    status: str
    old_sha256: str | None
    new_sha256: str | None
    old_size: int | None
    new_size: int | None


@dataclass(frozen=True)
class DeltaManifest:
    old_root: str
    new_root: str
    entries: tuple[DeltaEntry, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def _digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def build_delta_manifest(old_root: Path, new_root: Path) -> DeltaManifest:
    old_root = old_root.expanduser().resolve()
    new_root = new_root.expanduser().resolve()
    if not old_root.is_dir() or not new_root.is_dir():
        raise ValueError("Both OTA roots must be directories")
    old_files = {p.relative_to(old_root).as_posix(): p for p in old_root.rglob("*") if p.is_file()}
    new_files = {p.relative_to(new_root).as_posix(): p for p in new_root.rglob("*") if p.is_file()}
    entries: list[DeltaEntry] = []
    for name in sorted(old_files.keys() | new_files.keys()):
        old = old_files.get(name)
        new = new_files.get(name)
        if old is None:
            entries.append(DeltaEntry(name, "added", None, _digest(new), None, new.stat().st_size))
        elif new is None:
            entries.append(DeltaEntry(name, "removed", _digest(old), None, old.stat().st_size, None))
        else:
            old_hash = _digest(old)
            new_hash = _digest(new)
            if old_hash != new_hash:
                entries.append(DeltaEntry(name, "modified", old_hash, new_hash, old.stat().st_size, new.stat().st_size))
    return DeltaManifest(str(old_root), str(new_root), tuple(entries))
