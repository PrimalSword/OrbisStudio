from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .avb import AvbReport, AvbTool
from .ext4 import DebugfsEditor, Ext4BuildManifest
from .sparse import SparseManifest, sparse_raw
from .super_builder import build_super


class PipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class PartitionPlan:
    name: str
    source_image: Path
    output_image: Path
    replacements: tuple[tuple[Path, str], ...] = ()
    removals: tuple[str, ...] = ()
    sparse_output: Path | None = None


@dataclass(frozen=True)
class PipelineResult:
    project: str
    partitions: tuple[dict[str, object], ...]
    super_manifest: dict[str, object] | None
    avb_reports: tuple[dict[str, object], ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str)


def load_plan(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PipelineError("Build plan root must be a JSON object")
    return data


def parse_partition_plans(data: dict[str, object], base: Path) -> tuple[PartitionPlan, ...]:
    raw_partitions = data.get("partitions", [])
    if not isinstance(raw_partitions, list):
        raise PipelineError("partitions must be an array")
    plans: list[PartitionPlan] = []
    for item in raw_partitions:
        if not isinstance(item, dict):
            raise PipelineError("Each partition plan must be an object")
        name = str(item.get("name", "")).strip()
        if not name:
            raise PipelineError("Partition name is required")
        source = (base / str(item.get("source", ""))).resolve()
        output = (base / str(item.get("output", ""))).resolve()
        replacements: list[tuple[Path, str]] = []
        for replacement in item.get("replace", []):
            if not isinstance(replacement, dict):
                raise PipelineError(f"Invalid replacement in {name}")
            replacements.append(((base / str(replacement["source"])).resolve(), str(replacement["destination"])))
        removals = tuple(str(value) for value in item.get("remove", []))
        sparse_value = item.get("sparse_output")
        sparse_output = (base / str(sparse_value)).resolve() if sparse_value else None
        plans.append(PartitionPlan(name, source, output, tuple(replacements), removals, sparse_output))
    return tuple(plans)


def run_pipeline(
    plan_path: Path,
    debugfs: Path | None = None,
    avbtool: Path | None = None,
) -> PipelineResult:
    plan_path = plan_path.resolve()
    data = load_plan(plan_path)
    base = plan_path.parent
    editor = DebugfsEditor(debugfs)
    partition_results: list[dict[str, object]] = []
    logical_images: dict[str, Path] = {}

    for plan in parse_partition_plans(data, base):
        if plan.replacements or plan.removals:
            manifest_path = plan.output_image.with_suffix(plan.output_image.suffix + ".manifest.json")
            manifest: Ext4BuildManifest = editor.build(
                source_image=plan.source_image,
                output_image=plan.output_image,
                replacements=plan.replacements,
                removals=plan.removals,
                manifest_path=manifest_path,
            )
            result: dict[str, object] = asdict(manifest)
        else:
            if plan.source_image != plan.output_image:
                plan.output_image.parent.mkdir(parents=True, exist_ok=True)
                plan.output_image.write_bytes(plan.source_image.read_bytes())
            result = {"source_image": str(plan.source_image), "output_image": str(plan.output_image), "changes": []}
        if plan.sparse_output is not None:
            sparse_manifest: SparseManifest = sparse_raw(plan.output_image, plan.sparse_output)
            result["sparse"] = sparse_manifest.as_dict()
        partition_results.append(result)
        logical_images[plan.name] = plan.output_image

    super_result: dict[str, object] | None = None
    super_plan = data.get("super")
    if isinstance(super_plan, dict) and super_plan.get("enabled", True):
        required = ("original", "profile", "output")
        missing = [name for name in required if not super_plan.get(name)]
        if missing:
            raise PipelineError(f"super plan missing: {', '.join(missing)}")
        super_result = build_super(
            original_super=(base / str(super_plan["original"])).resolve(),
            logical_images=logical_images,
            profile_path=(base / str(super_plan["profile"])).resolve(),
            output=(base / str(super_plan["output"])).resolve(),
        )

    avb_reports: list[dict[str, object]] = []
    avb_plan = data.get("avb")
    if isinstance(avb_plan, dict) and avb_plan.get("verify"):
        tool = AvbTool(avbtool)
        images: Iterable[object] = avb_plan.get("images", [])
        for image in images:
            report: AvbReport = tool.verify((base / str(image)).resolve())
            avb_reports.append(asdict(report))
            if not report.verified and avb_plan.get("strict", True):
                raise PipelineError(f"AVB verification failed: {image}\n{report.verification_output}")

    result = PipelineResult(str(base), tuple(partition_results), super_result, tuple(avb_reports))
    report_path = data.get("report")
    if report_path:
        target = (base / str(report_path)).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result.to_json() + "\n", encoding="utf-8")
    return result
