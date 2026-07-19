from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


class AndroidConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class FstabEntry:
    source: str
    mount_point: str
    fs_type: str
    mount_flags: tuple[str, ...]
    fs_mgr_flags: tuple[str, ...]
    line_number: int


@dataclass(frozen=True)
class FileContextRule:
    pattern: str
    context: str
    line_number: int


def parse_fstab(path: Path) -> tuple[FstabEntry, ...]:
    if not path.is_file():
        raise AndroidConfigError(f"fstab does not exist: {path}")
    entries: list[FstabEntry] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) < 4:
            raise AndroidConfigError(f"Invalid fstab line {number}: expected at least 4 fields")
        source, mount_point, fs_type, mount_flags = fields[:4]
        fs_mgr = fields[4] if len(fields) > 4 else ""
        entries.append(FstabEntry(source, mount_point, fs_type, tuple(x for x in mount_flags.split(",") if x), tuple(x for x in fs_mgr.split(",") if x), number))
    return tuple(entries)


def parse_file_contexts(path: Path) -> tuple[FileContextRule, ...]:
    if not path.is_file():
        raise AndroidConfigError(f"file_contexts does not exist: {path}")
    rules: list[FileContextRule] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 2:
            raise AndroidConfigError(f"Invalid file_contexts line {number}")
        pattern, context = fields[0], fields[-1]
        try:
            re.compile(pattern)
        except re.error as error:
            raise AndroidConfigError(f"Invalid regex at file_contexts line {number}: {error}") from error
        rules.append(FileContextRule(pattern, context, number))
    return tuple(rules)


def resolve_context(path: str, rules: tuple[FileContextRule, ...]) -> str | None:
    for rule in rules:
        if re.fullmatch(rule.pattern, path):
            return rule.context
    return None
