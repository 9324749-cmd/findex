from __future__ import annotations

from pathlib import Path

import pytest

from findex.index import build_index, build_partial, merge


def _signature(index):
    return (
        {term: tuple((p.doc_id, p.tf, p.positions) for p in postings) for term, postings in index.items()},
        {doc_id: (meta.doc_id, meta.path, meta.title, meta.length) for doc_id, meta in index.documents.items()},
        index.texts,
    )


def test_merge_of_partials_matches_lab04_serial_index(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.txt").write_text("Python threads and processes", encoding="utf-8")
    (corpus / "b.txt").write_text("Processes use separate memory", encoding="utf-8")
    (corpus / "c.txt").write_text("Python indexing", encoding="utf-8")
    files = sorted(str(path) for path in corpus.glob("*.txt"))
    expected = build_index(corpus)
    partials = [build_partial(files[:2], str(corpus)), build_partial(files[2:], str(corpus))]
    actual = merge(partials)
    assert _signature(actual) == _signature(expected)


@pytest.mark.parametrize("executor", ["serial", "threads", "processes"])
def test_executor_build_matches_serial(tmp_path: Path, executor: str) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for number in range(5):
        (corpus / f"doc_{number}.txt").write_text(f"shared term{number} python", encoding="utf-8")
    expected = build_index(corpus)
    actual = build_index(corpus, workers=2, executor=executor)
    assert _signature(actual) == _signature(expected)


def test_merge_rejects_duplicate_document_ids(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "same.txt").write_text("duplicate", encoding="utf-8")
    partial = build_partial([str(corpus / "same.txt")], str(corpus))
    with pytest.raises(ValueError, match="Повторні doc_id"):
        merge([partial, partial])


def test_build_index_rejects_invalid_executor(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    with pytest.raises(ValueError, match="executor"):
        build_index(corpus, executor="invalid")  # type: ignore[arg-type] -- exercise runtime validation


def test_cli_index_accepts_executor_options(tmp_path: Path) -> None:
    from typer.testing import CliRunner
    from findex.cli import app

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "one.txt").write_text("parallel indexing", encoding="utf-8")
    output = tmp_path / "index.bin"
    result = CliRunner().invoke(
        app,
        ["index", str(corpus), "--out", str(output), "--executor", "processes", "--workers", "2"],
    )
    assert result.exit_code == 0, result.output
    assert output.exists()
