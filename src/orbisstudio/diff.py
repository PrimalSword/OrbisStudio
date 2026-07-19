from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json


@dataclass
class TreeDiff:
    modified: list[str]
    added: list[str]
    deleted: list[str]

    @property
    def clean(self) -> bool:
        return not (self.modified or self.added or self.deleted)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compare_trees(stock: Path, work: Path) -> TreeDiff:
    stock_files = {p.relative_to(stock): p for p in stock.rglob("*") if p.is_file()}
    work_files = {p.relative_to(work): p for p in work.rglob("*") if p.is_file()}

    modified: list[str] = []
    added: list[str] = []
    deleted: list[str] = []

    for relative, work_file in work_files.items():
        stock_file = stock_files.get(relative)
        if stock_file is None:
            added.append(relative.as_posix())
            continue
        if work_file.stat().st_size != stock_file.stat().st_size:
            modified.append(relative.as_posix())
            continue
        if sha256(work_file) != sha256(stock_file):
            modified.append(relative.as_posix())

    for relative in stock_files:
        if relative not in work_files:
            deleted.append(relative.as_posix())

    return TreeDiff(sorted(modified), sorted(added), sorted(deleted))
