from pathlib import Path

from findex.index import build_index
from findex.models import DocMeta, Posting
from findex.search import merge_and, merge_or, search
from findex.store import load_index, save_index


def make_corpus(root: Path):
    (root / "001.txt").write_text("apple banana apple", encoding="utf-8")
    (root / "002.txt").write_text("banana cherry", encoding="utf-8")
    (root / "003.txt").write_text("cherry apple", encoding="utf-8")


def test_build_index_and_postings(tmp_path):
    make_corpus(tmp_path)
    index = build_index(tmp_path)
    assert index.doc_lengths == {1: 3, 2: 2, 3: 2}
    assert [(p.doc_id, p.tf) for p in index.postings["apple"]] == [(1, 2), (3, 1)]
    assert index.doc_meta[1].title == "001"


def test_merge_functions():
    assert merge_and([1, 2, 4], [2, 3, 4]) == [2, 4]
    assert merge_or([1, 2, 4], [2, 3, 4]) == [1, 2, 3, 4]


def test_boolean_search_engines_agree(tmp_path):
    make_corpus(tmp_path)
    index = build_index(tmp_path)
    for query, expected in [
        ("apple banana", [1]),
        ("apple OR cherry", [1, 2, 3]),
        ("apple AND NOT banana", [3]),
        ("NOT banana", [3]),
        ("(apple OR cherry) AND banana", [1, 2]),
    ]:
        assert search(index, query, engine="merge") == expected
        assert search(index, query, engine="set") == expected


def test_positions_are_optional(tmp_path):
    make_corpus(tmp_path)
    index = build_index(tmp_path, positions=True)
    assert index.positions_enabled
    assert index.postings["apple"][0].positions == (0, 2)


def test_models_are_hashable():
    assert len({Posting(1, 2), Posting(1, 2)}) == 1
    assert len({DocMeta(1, "a.txt", "a"), DocMeta(1, "a.txt", "a")}) == 1


def test_pickle_and_json_roundtrip(tmp_path):
    make_corpus(tmp_path)
    index = build_index(tmp_path)
    for fmt, name in [("pickle", "index.bin"), ("json", "index.json")]:
        target = tmp_path / name
        save_index(index, target, fmt=fmt)
        loaded = load_index(target)
        assert loaded.doc_lengths == index.doc_lengths
        assert loaded.postings == index.postings
        assert loaded.doc_meta == index.doc_meta
