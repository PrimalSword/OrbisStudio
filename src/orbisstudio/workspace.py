from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


class WorkspaceError(RuntimeError):
    """Raised when a firmware workspace cannot be created or inspected safely."""


@dataclass(frozen=True)
class FirmwareArtifact:
    name: str
    source: str
    stock_path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class WorkspaceManifest:
    schema_version: int
    name: str
    created_at: str
    root: str
    artifacts: tuple[FirmwareArtifact, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


@dataclass(frozen=True)
class WorkspaceLayout:
    root: Path
    stock: Path
    logical: Path
    work: Path
    output: Path
    reports: Path
    profiles: Path
    backups: Path
    manifest: Path

    @classmethod
    def create(cls, root: Path) -> "WorkspaceLayout":
        root = root.expanduser().resolve()
        layout = cls(
            root=root,
            stock=root / "Stock",
            logical=root / "Logical",
            work=root / "Work",
            output=root / "Output",
            reports=root / "Reports",
            profiles=root / "Profiles",
            backups=root / "Backups",
            manifest=root / ".orbis.json",
        )
        for directory in (
            layout.root,
            layout.stock,
            layout.logical,
            layout.work,
            layout.output,
            layout.reports,
            layout.profiles,
            layout.backups,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return layout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _firmware_images(source: Path) -> tuple[Path, ...]:
    if source.is_file():
        return (source,) if source.suffix.lower() in {".img", ".bin"} else ()
    if not source.is_dir():
        return ()
    return tuple(
        sorted(
            path
            for path in source.iterdir()
            if path.is_file() and path.suffix.lower() in {".img", ".bin"}
        )
    )


def create_workspace(
    source: Path,
    destination: Path,
    name: str | None = None,
    copy_to_work: bool = False,
) -> WorkspaceManifest:
    source = source.expanduser().resolve()
    images = _firmware_images(source)
    if not images:
        raise WorkspaceError(f"no .img or .bin firmware artifacts found in: {source}")

    layout = WorkspaceLayout.create(destination)
    if layout.manifest.exists():
        raise WorkspaceError(f"workspace already exists: {layout.root}")

    artifacts: list[FirmwareArtifact] = []
    for image in images:
        target = layout.stock / image.name
        if target.exists():
            raise WorkspaceError(f"refusing to overwrite stock artifact: {target}")
        shutil.copy2(image, target)
        digest = _sha256(target)
        artifacts.append(
            FirmwareArtifact(
                name=image.name,
                source=str(image),
                stock_path=str(target),
                size=target.stat().st_size,
                sha256=digest,
            )
        )
        if copy_to_work:
            shutil.copy2(target, layout.work / image.name)

    project_name = name or destination.expanduser().resolve().name
    manifest = WorkspaceManifest(
        schema_version=1,
        name=project_name,
        created_at=datetime.now(timezone.utc).isoformat(),
        root=str(layout.root),
        artifacts=tuple(artifacts),
    )
    layout.manifest.write_text(manifest.to_json() + "\n", encoding="utf-8")
    return manifest


def load_workspace(root: Path) -> WorkspaceManifest:
    layout = WorkspaceLayout.create(root)
    if not layout.manifest.is_file():
        raise WorkspaceError(f"workspace manifest not found: {layout.manifest}")
    data = json.loads(layout.manifest.read_text(encoding="utf-8"))
    artifacts = tuple(FirmwareArtifact(**item) for item in data.get("artifacts", []))
    return WorkspaceManifest(
        schema_version=int(data["schema_version"]),
        name=str(data["name"]),
        created_at=str(data["created_at"]),
        root=str(data["root"]),
        artifacts=artifacts,
    )


def verify_workspace(root: Path) -> dict[str, object]:
    manifest = load_workspace(root)
    items: list[dict[str, object]] = []
    ready = True
    for artifact in manifest.artifacts:
        path = Path(artifact.stock_path)
        if not path.is_file():
            items.append({"name": artifact.name, "status": "missing", "path": str(path)})
            ready = False
            continue
        actual = _sha256(path)
        status = "verified" if actual == artifact.sha256 else "mismatch"
        ready = ready and status == "verified"
        items.append(
            {
                "name": artifact.name,
                "status": status,
                "path": str(path),
                "expected_sha256": artifact.sha256,
                "actual_sha256": actual,
                "size": path.stat().st_size,
            }
        )
    return {"workspace": manifest.root, "name": manifest.name, "items": items, "ready": ready}
