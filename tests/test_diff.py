from pathlib import Path

from orbisstudio.diff import compare_trees


def test_compare_trees(tmp_path: Path) -> None:
    stock = tmp_path / "Stock"
    work = tmp_path / "Work"
    stock.mkdir()
    work.mkdir()

    (stock / "same.txt").write_text("same", encoding="utf-8")
    (work / "same.txt").write_text("same", encoding="utf-8")
    (stock / "modified.txt").write_text("old", encoding="utf-8")
    (work / "modified.txt").write_text("new", encoding="utf-8")
    (stock / "deleted.txt").write_text("gone", encoding="utf-8")
    (work / "added.txt").write_text("new", encoding="utf-8")

    result = compare_trees(stock, work)

    assert result.modified == ["modified.txt"]
    assert result.added == ["added.txt"]
    assert result.deleted == ["deleted.txt"]
