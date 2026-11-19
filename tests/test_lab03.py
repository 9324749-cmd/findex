from findex.index import Index, build_index, save_index, open_index
from findex.models import Posting, DocMeta
from findex.query import parse, Term, And, Or, Not, Phrase
from findex.ranking import BM25, TfIdf, search
from pathlib import Path

def make_index(tmp_path):
    (tmp_path/"a.txt").write_text("python async await event loop", encoding="utf-8")
    (tmp_path/"b.txt").write_text("python python common common common", encoding="utf-8")
    (tmp_path/"c.txt").write_text("java event loop", encoding="utf-8")
    return build_index(tmp_path)

def test_mapping_api(tmp_path):
    ix=make_index(tmp_path)
    assert len(ix) > 0 and "python" in ix and ix["python"]
    assert list(iter(ix)) and repr(ix).startswith("Index(")
    assert ix.num_docs == 3 and ix.avg_doc_length > 0 and ix.df("python") == 2

def test_context_manager_closes_even_on_error(tmp_path):
    ix=make_index(tmp_path); path=tmp_path/"index.bin"; save_index(ix,path)
    try:
        with open_index(path) as opened:
            assert opened.num_docs == 3
            raise RuntimeError("test")
    except RuntimeError: pass
    assert opened.closed

def test_query_tree_equality_and_precedence():
    assert parse("a OR b c") == Or(Term("a"), And(Term("b"), Term("c")))
    assert parse("a AND (b OR c) NOT d") == And(And(Term("a"), Or(Term("b"), Term("c"))), Not(Term("d")))
    assert parse('"event loop"') == Phrase("event loop")

def test_boolean_and_phrase(tmp_path):
    ix=make_index(tmp_path)
    assert parse("python AND async").evaluate(ix) == {"a.txt"}
    assert parse('"event loop"').evaluate(ix) == {"a.txt", "c.txt"}
    assert parse("python NOT async").evaluate(ix) == {"b.txt"}

def test_ranking_returns_top_k(tmp_path):
    ix=make_index(tmp_path)
    results=search(ix,"python",BM25(),k=1)
    assert len(results)==1 and results[0].doc_id in {"a.txt","b.txt"}
    assert search(ix,"python",TfIdf(),k=2)

def test_serialization_json(tmp_path):
    ix=make_index(tmp_path); path=tmp_path/"ix.json"; save_index(ix,path,"json")
    with open_index(path) as loaded: assert loaded.num_docs==3 and "python" in loaded


def test_cache_hit_and_snippet_highlight(tmp_path, caplog):
    import logging
    ix=make_index(tmp_path)
    with caplog.at_level(logging.INFO):
        first=search(ix, "python AND async", BM25(), k=5)
        second=search(ix, "python AND async", BM25(), k=5)
    assert first and second
    assert "[cache] HIT" in caplog.text
    assert "**python**" in first[0].snippet

def test_search_result_ordering():
    from findex.ranking import SearchResult
    results=[SearchResult("b", 2.0, "B"), SearchResult("a", 1.0, "A")]
    assert sorted(results)[0].doc_id == "a"


def test_merge_and_set_engines_agree(tmp_path):
    ix=make_index(tmp_path)
    query=parse("python AND (async OR java)")
    assert query.evaluate(ix, "merge") == query.evaluate(ix, "set")


def test_close_releases_index_data(tmp_path):
    ix = make_index(tmp_path)
    assert ix.num_docs == 3
    _ = ix.avg_doc_length
    ix.close()
    assert ix.closed
    assert ix.num_docs == 0
    assert len(ix) == 0


def test_bm25_saturation_component():
    scorer = BM25()
    component = lambda tf: (tf * (scorer.k1 + 1)) / (tf + scorer.k1)
    first = component(1) - component(0)
    twentieth = component(20) - component(19)
    assert twentieth < first
