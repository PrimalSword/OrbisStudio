from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class Partition:
    name: str
    offset: int
    size: int
    type_guid: str = ""
    unique_guid: str = ""
    attributes: int = 0


@dataclass
class ProjectLayout:
    root: Path
    stock: Path
    work: Path
    build: Path
    reports: Path
    profiles: Path

    @classmethod
    def create(cls, root: Path) -> "ProjectLayout":
        layout = cls(
            root=root,
            stock=root / "Stock",
            work=root / "Work",
            build=root / "Build",
            reports=root / "Reports",
            profiles=root / "Profiles",
        )
        for path in asdict(layout).values():
            Path(path).mkdir(parents=True, exist_ok=True)
        return layout


@dataclass
class BuildReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
