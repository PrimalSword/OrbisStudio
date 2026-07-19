from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json

from .android_config import FileContextRule, resolve_context


@dataclass(frozen=True)
class ContextFinding:
    path: str
    issue: str
    expected_context: str | None


@dataclass(frozen=True)
class ContextAuditReport:
    root: str
    scanned: int
    findings: tuple[ContextFinding, ...]

    @property
    def clean(self) -> bool:
        return not self.findings

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def audit_tree(root: Path, rules: tuple[FileContextRule, ...], android_prefix: str = "") -> ContextAuditReport:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Tree root does not exist: {root}")
    prefix = "/" + android_prefix.strip("/") if android_prefix.strip("/") else ""
    findings: list[ContextFinding] = []
    scanned = 0
    for item in sorted(root.rglob("*")):
        relative = item.relative_to(root).as_posix()
        android_path = f"{prefix}/{relative}"
        scanned += 1
        expected = resolve_context(android_path, rules)
        if expected is None:
            findings.append(ContextFinding(android_path, "no_matching_file_context_rule", None))
    return ContextAuditReport(str(root), scanned, tuple(findings))
