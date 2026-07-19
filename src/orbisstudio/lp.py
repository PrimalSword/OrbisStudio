from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class LinearExtent:
    partition: str
    offset: int
    size: int


def load_profile(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "metadata_slots" not in data:
        raise ValueError("Perfil LP inválido: metadata_slots ausente")
    return data


def first_valid_slot(profile: dict[str, Any]) -> dict[str, Any]:
    for slot in profile["metadata_slots"]:
        if slot.get("valid"):
            return slot
    raise ValueError("Perfil LP não contém slot válido")


def linear_extents(profile: dict[str, Any]) -> dict[str, LinearExtent]:
    slot = first_valid_slot(profile)
    extents = slot["extents"]
    result: dict[str, LinearExtent] = {}

    for partition in slot["partitions"]:
        name = partition["name"]
        if partition["num_extents"] != 1:
            continue
        extent = extents[partition["first_extent_index"]]
        if extent["target_type"] != 0:
            continue
        result[name] = LinearExtent(
            partition=name,
            offset=int(extent["target_data"]) * 512,
            size=int(partition["size_bytes"]),
        )
    return result
