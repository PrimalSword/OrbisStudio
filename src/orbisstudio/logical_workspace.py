from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from .lp import LinearExtent, linear_extents, load_profile
from .workspace import WorkspaceError, WorkspaceLayout, load_workspace, verify_workspace


@dataclass(frozen=True)
class LogicalArtifact:
    name: str
    image_path: str
    work_path: str | None
    offset: int
    size: int
    sha256: str


@dataclass(frozen=True)
class LogicalExtractionReport:
    workspace: str
    super_image: str
    profile: str
    artifacts: tuple[LogicalArtifact, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_extent(source: Path, destination: Path, extent: LinearExtent) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()

    remaining = extent.size
    try:
        with source.open("rb") as input_stream, temporary.open("wb") as output_stream:
            input_stream.seek(extent.offset)
            while remaining:
                chunk = input_stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise WorkspaceError(
                        f"super image truncated while extracting {extent.partition}"
                    )
                output_stream.write(chunk)
                remaining -= len(chunk)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def extract_logical_partitions(
    workspace: Path,
    profile_path: Path,
    super_name: str = "super.img",
    copy_to_work: bool = True,
    overwrite: bool = False,
) -> LogicalExtractionReport:
    workspace = workspace.expanduser().resolve()
    layout = WorkspaceLayout.create(workspace)
    load_workspace(workspace)

    integrity = verify_workspace(workspace)
    if not integrity["ready"]:
        raise WorkspaceError("workspace Stock integrity verification failed")

    super_image = layout.stock / super_name
    if not super_image.is_file():
        raise WorkspaceError(f"stock super image not found: {super_image}")

    profile_path = profile_path.expanduser().resolve()
    profile = load_profile(profile_path)
    extents = linear_extents(profile)
    if not extents:
        raise WorkspaceError("LP profile contains no supported linear extents")

    super_size = super_image.stat().st_size
    artifacts: list[LogicalArtifact] = []
    for name, extent in sorted(extents.items()):
        if extent.offset < 0 or extent.size <= 0 or extent.offset + extent.size > super_size:
            raise WorkspaceError(
                f"invalid extent for {name}: offset={extent.offset}, size={extent.size}, "
                f"super_size={super_size}"
            )

        logical_path = layout.logical / f"{name}.img"
        work_path = layout.work / f"{name}.img" if copy_to_work else None
        targets = [logical_path] + ([work_path] if work_path is not None else [])
        existing = [path for path in targets if path is not None and path.exists()]
        if existing and not overwrite:
            raise WorkspaceError(f"refusing to overwrite logical artifact: {existing[0]}")

        _copy_extent(super_image, logical_path, extent)
        if work_path is not None:
            shutil.copy2(logical_path, work_path)

        artifacts.append(
            LogicalArtifact(
                name=name,
                image_path=str(logical_path),
                work_path=str(work_path) if work_path is not None else None,
                offset=extent.offset,
                size=extent.size,
                sha256=_sha256(logical_path),
            )
        )

    report = LogicalExtractionReport(
        workspace=str(workspace),
        super_image=str(super_image),
        profile=str(profile_path),
        artifacts=tuple(artifacts),
    )
    report_path = layout.reports / "logical-map.json"
    report_path.write_text(report.to_json() + "\n", encoding="utf-8")
    return report
