from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path

LP_GEOMETRY_MAGIC = 0x616C4467
LP_HEADER_MAGIC = 0x414C5030
LP_RESERVED_BYTES = 4096
LP_GEOMETRY_SIZE = 4096
LP_SECTOR_SIZE = 512


class LpMetadataError(RuntimeError):
    """Raised when Android logical-partition metadata is invalid or unsupported."""


@dataclass(frozen=True)
class LpGeometry:
    offset: int
    valid: bool
    metadata_max_size: int
    metadata_slot_count: int
    logical_block_size: int
    error: str | None = None


@dataclass(frozen=True)
class LpMetadataCopy:
    location: str
    slot: int
    offset: int
    valid: bool
    major_version: int | None
    minor_version: int | None
    header_size: int | None
    tables_size: int | None
    partitions: tuple[dict[str, object], ...]
    extents: tuple[dict[str, object], ...]
    groups: tuple[dict[str, object], ...]
    block_devices: tuple[dict[str, object], ...]
    error: str | None = None


@dataclass(frozen=True)
class LpInspectionReport:
    image: str
    image_size: int
    sector_size: int
    geometry: LpGeometry
    metadata_slots: tuple[LpMetadataCopy, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def _read_exact(stream: object, offset: int, size: int) -> bytes:
    stream.seek(offset)  # type: ignore[attr-defined]
    data = stream.read(size)  # type: ignore[attr-defined]
    if len(data) != size:
        raise LpMetadataError(f"truncated image at offset {offset}: expected {size} bytes")
    return data


def _checksum_valid(data: bytes, checksum_offset: int) -> bool:
    if checksum_offset + 32 > len(data):
        return False
    expected = data[checksum_offset : checksum_offset + 32]
    mutable = bytearray(data)
    mutable[checksum_offset : checksum_offset + 32] = bytes(32)
    return hashlib.sha256(mutable).digest() == expected


def _decode_name(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def _parse_geometry(stream: object, image_size: int) -> LpGeometry:
    errors: list[str] = []
    for offset in (LP_RESERVED_BYTES, LP_RESERVED_BYTES + LP_GEOMETRY_SIZE):
        try:
            prefix = _read_exact(stream, offset, 52)
            magic, struct_size = struct.unpack_from("<II", prefix, 0)
            if magic != LP_GEOMETRY_MAGIC:
                raise LpMetadataError(f"bad geometry magic 0x{magic:08x}")
            if struct_size < 52 or struct_size > LP_GEOMETRY_SIZE:
                raise LpMetadataError(f"invalid geometry struct size: {struct_size}")
            raw = _read_exact(stream, offset, struct_size)
            if not _checksum_valid(raw, 8):
                raise LpMetadataError("geometry checksum mismatch")
            metadata_max_size, metadata_slot_count, logical_block_size = struct.unpack_from(
                "<III", raw, 40
            )
            metadata_start = LP_RESERVED_BYTES + 2 * LP_GEOMETRY_SIZE
            required = metadata_start + 2 * metadata_max_size * metadata_slot_count
            if metadata_max_size <= 0 or metadata_slot_count <= 0 or required > image_size:
                raise LpMetadataError("geometry describes invalid metadata regions")
            return LpGeometry(offset, True, metadata_max_size, metadata_slot_count, logical_block_size)
        except LpMetadataError as error:
            errors.append(f"offset {offset}: {error}")
    return LpGeometry(LP_RESERVED_BYTES, False, 0, 0, 0, "; ".join(errors))


def _descriptor(header: bytes, offset: int) -> tuple[int, int, int]:
    return struct.unpack_from("<III", header, offset)


def _slice_table(tables: bytes, descriptor: tuple[int, int, int], label: str) -> list[bytes]:
    table_offset, count, entry_size = descriptor
    if count and entry_size <= 0:
        raise LpMetadataError(f"{label} descriptor has zero entry size")
    end = table_offset + count * entry_size
    if table_offset > len(tables) or end > len(tables):
        raise LpMetadataError(f"{label} table exceeds metadata tables region")
    return [tables[table_offset + i * entry_size : table_offset + (i + 1) * entry_size] for i in range(count)]


def _parse_copy(stream: object, location: str, slot: int, offset: int, max_size: int) -> LpMetadataCopy:
    empty: tuple[dict[str, object], ...] = ()
    try:
        prefix = _read_exact(stream, offset, 128)
        magic, major, minor, header_size = struct.unpack_from("<IHHI", prefix, 0)
        if magic != LP_HEADER_MAGIC:
            raise LpMetadataError(f"bad metadata magic 0x{magic:08x}")
        if header_size < 128 or header_size > max_size:
            raise LpMetadataError(f"invalid metadata header size: {header_size}")
        header = _read_exact(stream, offset, header_size)
        if not _checksum_valid(header, 12):
            raise LpMetadataError("metadata header checksum mismatch")
        tables_size = struct.unpack_from("<I", header, 44)[0]
        if header_size + tables_size > max_size:
            raise LpMetadataError("metadata header and tables exceed slot size")
        tables = _read_exact(stream, offset + header_size, tables_size)
        if hashlib.sha256(tables).digest() != header[48:80]:
            raise LpMetadataError("metadata tables checksum mismatch")

        partitions: list[dict[str, object]] = []
        for entry in _slice_table(tables, _descriptor(header, 80), "partition"):
            if len(entry) < 52:
                raise LpMetadataError("partition entry is smaller than 52 bytes")
            attributes, first_extent_index, num_extents, group_index = struct.unpack_from("<IIII", entry, 36)
            partitions.append({"name": _decode_name(entry[:36]), "attributes": attributes, "first_extent_index": first_extent_index, "num_extents": num_extents, "group_index": group_index, "size_bytes": 0})

        extents: list[dict[str, object]] = []
        for entry in _slice_table(tables, _descriptor(header, 92), "extent"):
            if len(entry) < 24:
                raise LpMetadataError("extent entry is smaller than 24 bytes")
            num_sectors, target_type, target_data, target_source = struct.unpack_from("<QIQI", entry, 0)
            extents.append({"num_sectors": num_sectors, "target_type": target_type, "target_data": target_data, "target_source": target_source, "size_bytes": num_sectors * LP_SECTOR_SIZE})

        for partition in partitions:
            first = int(partition["first_extent_index"])
            count = int(partition["num_extents"])
            if first + count > len(extents):
                raise LpMetadataError(f"partition {partition['name']} references invalid extents")
            partition["size_bytes"] = sum(int(item["size_bytes"]) for item in extents[first : first + count])

        groups: list[dict[str, object]] = []
        for entry in _slice_table(tables, _descriptor(header, 104), "group"):
            if len(entry) < 48:
                raise LpMetadataError("group entry is smaller than 48 bytes")
            flags, maximum_size = struct.unpack_from("<IQ", entry, 36)
            groups.append({"name": _decode_name(entry[:36]), "flags": flags, "maximum_size": maximum_size})

        block_devices: list[dict[str, object]] = []
        for entry in _slice_table(tables, _descriptor(header, 116), "block device"):
            if len(entry) < 64:
                raise LpMetadataError("block-device entry is smaller than 64 bytes")
            first_sector, alignment, alignment_offset, size = struct.unpack_from("<QIIQ", entry, 0)
            flags = struct.unpack_from("<I", entry, 60)[0]
            block_devices.append({"first_logical_sector": first_sector, "alignment": alignment, "alignment_offset": alignment_offset, "size": size, "partition_name": _decode_name(entry[24:60]), "flags": flags})

        return LpMetadataCopy(location, slot, offset, True, major, minor, header_size, tables_size, tuple(partitions), tuple(extents), tuple(groups), tuple(block_devices))
    except LpMetadataError as error:
        return LpMetadataCopy(location, slot, offset, False, None, None, None, None, empty, empty, empty, empty, str(error))


def inspect_lp_metadata(image: Path) -> LpInspectionReport:
    image = image.expanduser().resolve()
    if not image.is_file():
        raise LpMetadataError(f"super image not found: {image}")
    image_size = image.stat().st_size
    with image.open("rb") as stream:
        geometry = _parse_geometry(stream, image_size)
        if not geometry.valid:
            raise LpMetadataError(geometry.error or "no valid LP geometry found")
        metadata_start = LP_RESERVED_BYTES + 2 * LP_GEOMETRY_SIZE
        primary_size = geometry.metadata_max_size * geometry.metadata_slot_count
        copies: list[LpMetadataCopy] = []
        for slot in range(geometry.metadata_slot_count):
            copies.append(_parse_copy(stream, "primary", slot, metadata_start + slot * geometry.metadata_max_size, geometry.metadata_max_size))
            copies.append(_parse_copy(stream, "backup", slot, metadata_start + primary_size + slot * geometry.metadata_max_size, geometry.metadata_max_size))
    if not any(copy.valid for copy in copies):
        errors = "; ".join(f"{copy.location}[{copy.slot}]: {copy.error}" for copy in copies)
        raise LpMetadataError(f"no valid LP metadata copies found: {errors}")
    return LpInspectionReport(str(image), image_size, LP_SECTOR_SIZE, geometry, tuple(copies))


def inspect_workspace_lp(workspace: Path, super_name: str = "super.img", output: Path | None = None) -> LpInspectionReport:
    from .workspace import WorkspaceLayout, load_workspace, verify_workspace

    workspace = workspace.expanduser().resolve()
    layout = WorkspaceLayout.create(workspace)
    load_workspace(workspace)
    integrity = verify_workspace(workspace)
    if not integrity["ready"]:
        raise LpMetadataError("workspace Stock integrity verification failed")
    report = inspect_lp_metadata(layout.stock / super_name)
    target = output.expanduser().resolve() if output else layout.profiles / "lp-profile.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.to_json() + "\n", encoding="utf-8")
    return report
