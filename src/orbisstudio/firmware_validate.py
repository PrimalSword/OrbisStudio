from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    path: str | None = None


@dataclass(frozen=True)
class FirmwareValidation:
    root: str
    ready: bool
    images: tuple[str, ...]
    issues: tuple[ValidationIssue, ...]
    hashes: dict[str, str]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def validate_firmware(root: Path, required: tuple[str, ...] = ("boot", "super", "vbmeta")) -> FirmwareValidation:
    root = root.expanduser().resolve()
    issues: list[ValidationIssue] = []
    if not root.is_dir():
        issues.append(ValidationIssue("error", "root_missing", "firmware directory does not exist", str(root)))
        return FirmwareValidation(str(root), False, (), tuple(issues), {})
    found = {path.stem: path for path in root.rglob("*.img") if path.is_file()}
    normalized = {name.removesuffix("_a").removesuffix("_b") for name in found}
    for name in required:
        if name not in normalized:
            issues.append(ValidationIssue("error", "partition_missing", f"required image is missing: {name}"))
    slot_a = {name[:-2] for name in found if name.endswith("_a")}
    slot_b = {name[:-2] for name in found if name.endswith("_b")}
    for name in sorted(slot_a ^ slot_b):
        issues.append(ValidationIssue("warning", "slot_asymmetry", f"partition exists in only one slot: {name}"))
    hashes: dict[str, str] = {}
    for name, path in sorted(found.items()):
        if path.stat().st_size == 0:
            issues.append(ValidationIssue("error", "empty_image", "image is empty", str(path)))
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
        hashes[name] = digest.hexdigest()
    ready = not any(item.severity == "error" for item in issues)
    return FirmwareValidation(str(root), ready, tuple(sorted(found)), tuple(issues), hashes)
