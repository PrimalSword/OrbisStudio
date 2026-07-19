from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class PropertyError(RuntimeError):
    pass


@dataclass(frozen=True)
class PropertyChange:
    key: str
    old_value: str | None
    new_value: str | None


def _split_property(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        return None
    key, value = line.split("=", 1)
    key = key.strip()
    if not key:
        return None
    return key, value.rstrip("\r\n")


def read_properties(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise PropertyError(f"Property file does not exist: {path}")
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="surrogateescape").splitlines():
        parsed = _split_property(line)
        if parsed:
            result[parsed[0]] = parsed[1]
    return result


def edit_properties(
    source: Path,
    output: Path,
    updates: dict[str, str],
    removals: Iterable[str] = (),
    append_missing: bool = True,
) -> tuple[PropertyChange, ...]:
    if not source.is_file():
        raise PropertyError(f"Property file does not exist: {source}")
    remove_set = set(removals)
    if remove_set & updates.keys():
        conflict = sorted(remove_set & updates.keys())
        raise PropertyError(f"Properties cannot be updated and removed together: {', '.join(conflict)}")

    raw = source.read_text(encoding="utf-8", errors="surrogateescape")
    newline = "\r\n" if "\r\n" in raw else "\n"
    trailing_newline = raw.endswith(("\n", "\r"))
    seen: set[str] = set()
    changes: list[PropertyChange] = []
    output_lines: list[str] = []

    for original in raw.splitlines():
        parsed = _split_property(original)
        if not parsed:
            output_lines.append(original)
            continue
        key, old_value = parsed
        if key in remove_set:
            seen.add(key)
            changes.append(PropertyChange(key, old_value, None))
            continue
        if key in updates:
            seen.add(key)
            new_value = updates[key]
            prefix = original.split("=", 1)[0]
            output_lines.append(f"{prefix}={new_value}")
            if old_value != new_value:
                changes.append(PropertyChange(key, old_value, new_value))
            continue
        output_lines.append(original)

    if append_missing:
        for key, value in updates.items():
            if key not in seen:
                output_lines.append(f"{key}={value}")
                changes.append(PropertyChange(key, None, value))

    output.parent.mkdir(parents=True, exist_ok=True)
    text = newline.join(output_lines)
    if trailing_newline or output_lines:
        text += newline
    output.write_text(text, encoding="utf-8", errors="surrogateescape")
    return tuple(changes)
