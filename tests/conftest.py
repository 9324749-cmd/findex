from __future__ import annotations
import pytest
from findex.index import build_index

@pytest.fixture
def tiny_corpus(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.txt").write_text("Python async await café", encoding="utf-8")
    (root / "b.txt").write_text("Python Python тестування", encoding="utf-8")
    (root / "c.txt").write_text("Java event loop café extra words here", encoding="utf-8")
    return root

@pytest.fixture
def tiny_index(tiny_corpus):
    return build_index(tiny_corpus)
