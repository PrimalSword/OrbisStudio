from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import binascii
import struct
import uuid

from .models import Partition


GPT_SIGNATURE = b"EFI PART"


@dataclass(frozen=True)
class GPTHeader:
    current_lba: int
    backup_lba: int
    first_usable_lba: int
    last_usable_lba: int
    disk_guid: str
    entries_lba: int
    entry_count: int
    entry_size: int


def _guid(raw: bytes) -> str:
    return str(uuid.UUID(bytes_le=raw))


def parse_gpt(image: Path, sector_size: int = 512) -> tuple[GPTHeader, list[Partition]]:
    with image.open("rb") as stream:
        stream.seek(sector_size)
        header_block = stream.read(sector_size)
        if header_block[:8] != GPT_SIGNATURE:
            raise ValueError("Assinatura GPT ausente no LBA 1")

        header_size = struct.unpack_from("<I", header_block, 12)[0]
        stored_crc = struct.unpack_from("<I", header_block, 16)[0]
        crc_buffer = bytearray(header_block[:header_size])
        struct.pack_into("<I", crc_buffer, 16, 0)
        calculated_crc = binascii.crc32(crc_buffer) & 0xFFFFFFFF
        if stored_crc != calculated_crc:
            raise ValueError(
                f"CRC do cabeçalho GPT inválido: esperado {stored_crc:#x}, calculado {calculated_crc:#x}"
            )

        current_lba, backup_lba = struct.unpack_from("<QQ", header_block, 24)
        first_usable, last_usable = struct.unpack_from("<QQ", header_block, 40)
        disk_guid = _guid(header_block[56:72])
        entries_lba = struct.unpack_from("<Q", header_block, 72)[0]
        entry_count, entry_size, entries_crc = struct.unpack_from("<III", header_block, 80)

        stream.seek(entries_lba * sector_size)
        entries_raw = stream.read(entry_count * entry_size)
        calculated_entries_crc = binascii.crc32(entries_raw) & 0xFFFFFFFF
        if calculated_entries_crc != entries_crc:
            raise ValueError(
                "CRC da tabela GPT inválido: "
                f"esperado {entries_crc:#x}, calculado {calculated_entries_crc:#x}"
            )

        header = GPTHeader(
            current_lba=current_lba,
            backup_lba=backup_lba,
            first_usable_lba=first_usable,
            last_usable_lba=last_usable,
            disk_guid=disk_guid,
            entries_lba=entries_lba,
            entry_count=entry_count,
            entry_size=entry_size,
        )

        partitions: list[Partition] = []
        for index in range(entry_count):
            entry = entries_raw[index * entry_size : (index + 1) * entry_size]
            if entry[:16] == bytes(16):
                continue
            first_lba, last_lba, attributes = struct.unpack_from("<QQQ", entry, 32)
            name = entry[56:entry_size].decode("utf-16-le", errors="ignore").rstrip("\x00")
            partitions.append(
                Partition(
                    name=name,
                    offset=first_lba * sector_size,
                    size=(last_lba - first_lba + 1) * sector_size,
                    type_guid=_guid(entry[:16]),
                    unique_guid=_guid(entry[16:32]),
                    attributes=attributes,
                )
            )

        return header, partitions
