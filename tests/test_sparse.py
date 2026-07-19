from __future__ import annotations

from pathlib import Path

import pytest

from orbisstudio.sparse import SparseError, inspect_sparse, is_sparse, sparse_raw, unsparse


def test_sparse_roundtrip(tmp_path: Path) -> None:
    raw = tmp_path / "raw.img"
    sparse = tmp_path / "raw.sparse.img"
    restored = tmp_path / "restored.img"
    payload = (b"OrbisStudio" * 1000) + bytes(777)
    raw.write_bytes(payload)

    manifest = sparse_raw(raw, sparse, block_size=4096, max_chunk_blocks=2)
    assert manifest.total_blocks == 4
    assert is_sparse(sparse)

    header, chunks = inspect_sparse(sparse)
    assert header.block_size == 4096
    assert header.total_blocks == 4
    assert len(chunks) == 2

    unsparse(sparse, restored)
    restored_bytes = restored.read_bytes()
    assert restored_bytes[: len(payload)] == payload
    assert restored_bytes[len(payload) :] == bytes(4096 * 4 - len(payload))


def test_refuses_source_overwrite(tmp_path: Path) -> None:
    image = tmp_path / "image.img"
    image.write_bytes(bytes(4096))
    with pytest.raises(SparseError):
        sparse_raw(image, image)


def test_rejects_non_sparse(tmp_path: Path) -> None:
    image = tmp_path / "bad.img"
    image.write_bytes(b"not sparse")
    with pytest.raises(SparseError):
        inspect_sparse(image)
