from __future__ import annotations

import hashlib
import io
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

SPARSE_MAGIC = 0xED26FF3A
CHUNK_RAW = 0xCAC1
CHUNK_FILL = 0xCAC2
CHUNK_DONT_CARE = 0xCAC3
CHUNK_CRC32 = 0xCAC4
_FILE_HEADER = struct.Struct("<IHHHHIIII")
_CHUNK_HEADER = struct.Struct("<HHII")


class SparseError(RuntimeError):
    pass


@dataclass(frozen=True)
class SparseHeader:
    major_version: int
    minor_version: int
    file_header_size: int
    chunk_header_size: int
    block_size: int
    total_blocks: int
    total_chunks: int
    image_checksum: int


@dataclass(frozen=True)
class SparseChunk:
    chunk_type: int
    output_blocks: int
    total_size: int
    data_offset: int


@dataclass(frozen=True)
class SparseManifest:
    source: str
    output: str
    source_sha256: str
    output_sha256: str
    block_size: int
    total_blocks: int
    total_chunks: int
    mode: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while data := handle.read(chunk_size):
            digest.update(data)
    return digest.hexdigest()


def is_sparse(path: Path) -> bool:
    with path.open("rb") as handle:
        raw = handle.read(4)
    return len(raw) == 4 and struct.unpack("<I", raw)[0] == SPARSE_MAGIC


def parse_sparse(handle: BinaryIO) -> tuple[SparseHeader, tuple[SparseChunk, ...]]:
    raw = handle.read(_FILE_HEADER.size)
    if len(raw) != _FILE_HEADER.size:
        raise SparseError("Truncated sparse file header")
    magic, major, minor, file_hsz, chunk_hsz, block_size, total_blocks, total_chunks, checksum = _FILE_HEADER.unpack(raw)
    if magic != SPARSE_MAGIC:
        raise SparseError("Not an Android sparse image")
    if major != 1:
        raise SparseError(f"Unsupported sparse major version: {major}")
    if file_hsz < _FILE_HEADER.size or chunk_hsz < _CHUNK_HEADER.size:
        raise SparseError("Invalid sparse header sizes")
    if block_size <= 0 or block_size % 4:
        raise SparseError(f"Invalid sparse block size: {block_size}")
    handle.seek(file_hsz)
    chunks: list[SparseChunk] = []
    produced = 0
    for _ in range(total_chunks):
        raw_chunk = handle.read(chunk_hsz)
        if len(raw_chunk) != chunk_hsz:
            raise SparseError("Truncated sparse chunk header")
        chunk_type, _reserved, output_blocks, total_size = _CHUNK_HEADER.unpack(raw_chunk[: _CHUNK_HEADER.size])
        payload_size = total_size - chunk_hsz
        if payload_size < 0:
            raise SparseError("Invalid sparse chunk size")
        if chunk_type == CHUNK_RAW and payload_size != output_blocks * block_size:
            raise SparseError("RAW chunk payload size mismatch")
        if chunk_type == CHUNK_FILL and payload_size != 4:
            raise SparseError("FILL chunk must contain four bytes")
        if chunk_type == CHUNK_DONT_CARE and payload_size != 0:
            raise SparseError("DONT_CARE chunk must not contain payload")
        if chunk_type == CHUNK_CRC32 and payload_size != 4:
            raise SparseError("CRC32 chunk must contain four bytes")
        if chunk_type not in {CHUNK_RAW, CHUNK_FILL, CHUNK_DONT_CARE, CHUNK_CRC32}:
            raise SparseError(f"Unsupported sparse chunk type: 0x{chunk_type:04x}")
        offset = handle.tell()
        chunks.append(SparseChunk(chunk_type, output_blocks, total_size, offset))
        handle.seek(payload_size, io.SEEK_CUR)
        if chunk_type != CHUNK_CRC32:
            produced += output_blocks
    if produced != total_blocks:
        raise SparseError(f"Sparse block count mismatch: header={total_blocks}, chunks={produced}")
    return SparseHeader(major, minor, file_hsz, chunk_hsz, block_size, total_blocks, total_chunks, checksum), tuple(chunks)


def inspect_sparse(path: Path) -> tuple[SparseHeader, tuple[SparseChunk, ...]]:
    with path.open("rb") as handle:
        return parse_sparse(handle)


def unsparse(source: Path, output: Path) -> SparseManifest:
    source = source.resolve()
    output = output.resolve()
    if source == output:
        raise SparseError("Refusing to overwrite source image")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".orbis.tmp")
    temp.unlink(missing_ok=True)
    with source.open("rb") as src:
        header, chunks = parse_sparse(src)
        with temp.open("wb") as dst:
            zero = bytes(min(header.block_size, 1024 * 1024))
            for chunk in chunks:
                src.seek(chunk.data_offset)
                byte_count = chunk.output_blocks * header.block_size
                if chunk.chunk_type == CHUNK_RAW:
                    remaining = byte_count
                    while remaining:
                        data = src.read(min(8 * 1024 * 1024, remaining))
                        if not data:
                            raise SparseError("Truncated RAW payload")
                        dst.write(data)
                        remaining -= len(data)
                elif chunk.chunk_type == CHUNK_FILL:
                    pattern = src.read(4)
                    if len(pattern) != 4:
                        raise SparseError("Truncated FILL payload")
                    repeated = pattern * (len(zero) // 4)
                    remaining = byte_count
                    while remaining:
                        data = repeated[: min(len(repeated), remaining)]
                        dst.write(data)
                        remaining -= len(data)
                elif chunk.chunk_type == CHUNK_DONT_CARE:
                    dst.seek(byte_count, io.SEEK_CUR)
                elif chunk.chunk_type == CHUNK_CRC32:
                    src.read(4)
            dst.truncate(header.total_blocks * header.block_size)
    temp.replace(output)
    return SparseManifest(str(source), str(output), sha256_file(source), sha256_file(output), header.block_size, header.total_blocks, header.total_chunks, "unsparse")


def _iter_blocks(handle: BinaryIO, block_size: int) -> Iterator[bytes]:
    while True:
        data = handle.read(block_size)
        if not data:
            return
        if len(data) < block_size:
            data += bytes(block_size - len(data))
        yield data


def sparse_raw(source: Path, output: Path, block_size: int = 4096, max_chunk_blocks: int = 1024) -> SparseManifest:
    source = source.resolve()
    output = output.resolve()
    if source == output:
        raise SparseError("Refusing to overwrite source image")
    if block_size <= 0 or block_size % 4:
        raise SparseError("Block size must be a positive multiple of four")
    size = source.stat().st_size
    total_blocks = (size + block_size - 1) // block_size
    chunks = (total_blocks + max_chunk_blocks - 1) // max_chunk_blocks
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".orbis.tmp")
    with source.open("rb") as src, temp.open("wb") as dst:
        dst.write(_FILE_HEADER.pack(SPARSE_MAGIC, 1, 0, _FILE_HEADER.size, _CHUNK_HEADER.size, block_size, total_blocks, chunks, 0))
        remaining = total_blocks
        while remaining:
            count = min(max_chunk_blocks, remaining)
            dst.write(_CHUNK_HEADER.pack(CHUNK_RAW, 0, count, _CHUNK_HEADER.size + count * block_size))
            for block in _iter_blocks(src, block_size):
                dst.write(block)
                count -= 1
                remaining -= 1
                if count == 0:
                    break
    temp.replace(output)
    return SparseManifest(str(source), str(output), sha256_file(source), sha256_file(output), block_size, total_blocks, chunks, "sparse-raw")
