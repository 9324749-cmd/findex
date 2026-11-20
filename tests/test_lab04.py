from __future__ import annotations
import json
from pathlib import Path
import pytest
from hypothesis import given, strategies as st
from typer.testing import CliRunner
from findex.cli import app
from findex.index import build_index, load_index, save_index
from findex.models import Posting
from findex.query import parse, Term, And, Or, Not, Phrase, QuerySyntaxError
from findex.ranking import BM25, TfIdf, search
from findex.tokenize import tokenize

runner = CliRunner()

@pytest.mark.parametrize(("source", "expected"), [
    ("Python python", ["python", "python"]), ("CAFÉ café", ["café", "café"]),
    ("Київ Україна", ["київ", "україна"]), ("naïve façade", ["naïve", "façade"]),
    ("hello_world", ["hello", "world"]), ("123 abc", ["123", "abc"]),
    ("Привіт, світе!", ["привіт", "світе"]), ("東京", ["東京"]),
    ("", []), ("... --- !!!", []), ("A—B", ["a", "b"]),
    ("добрий-день", ["добрий", "день"]),
])
def test_tokenizer_parametrized(source, expected):
    assert list(tokenize(source)) == expected

@pytest.mark.parametrize("query, expected", [
    ("alpha", Term("alpha")), ("alpha AND beta", And(Term("alpha"), Term("beta"))),
    ("alpha OR beta", Or(Term("alpha"), Term("beta"))),
    ("NOT alpha", Not(Term("alpha"))), ('"event loop"', Phrase("event loop")),
    ("alpha OR beta gamma", Or(Term("alpha"), And(Term("beta"), Term("gamma")))),
    ("alpha AND (beta OR gamma)", And(Term("alpha"), Or(Term("beta"), Term("gamma")))),
])
def test_parser_ast(query, expected):
    assert parse(query) == expected

@pytest.mark.parametrize("query", ["", "AND a", "a OR", "(a", "a)", "a AND OR b"])
def test_parser_rejects_invalid_queries(query):
    with pytest.raises(QuerySyntaxError):
        parse(query)

def test_fixture_builds_index(tiny_index):
    assert tiny_index.num_docs == 3
    assert "python" in tiny_index
    assert tiny_index.df("python") == 2

def test_merge_and_set_match_on_fixture(tiny_index):
    for q in ("python AND café", "python OR java", "NOT java", "python AND (async OR java)"):
        assert parse(q).evaluate(tiny_index, "merge") == parse(q).evaluate(tiny_index, "set")

@pytest.mark.parametrize("scorer", [BM25(), TfIdf()])
def test_both_scorers_return_results(tiny_index, scorer):
    results = search(tiny_index, "python", scorer=scorer, k=5)
    assert results
    assert all(result.score >= 0 for result in results)
    assert results[0].doc_id in {"a.txt", "b.txt"}

def test_save_load_pickle_roundtrip(tiny_index, tmp_path):
    path = tmp_path / "index.bin"
    save_index(tiny_index, path)
    loaded = load_index(path)
    assert loaded.num_docs == tiny_index.num_docs
    assert dict(loaded) == dict(tiny_index)
    assert loaded.documents == tiny_index.documents

def test_save_load_json_roundtrip(tiny_index, tmp_path):
    path = tmp_path / "index.json"
    save_index(tiny_index, path, "json")
    loaded = load_index(path)
    assert dict(loaded) == dict(tiny_index)

def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "index" in result.stdout and "search" in result.stdout and "stats" in result.stdout

def test_cli_index_and_json_search(tiny_corpus, tmp_path):
    index_path = tmp_path / "index.bin"
    built = runner.invoke(app, ["index", str(tiny_corpus), "--out", str(index_path)])
    assert built.exit_code == 0
    found = runner.invoke(app, ["search", "python", "--index", str(index_path), "--json"])
    assert found.exit_code == 0
    assert json.loads(found.stdout)

def test_cli_missing_index_is_clean_error(tmp_path):
    result = runner.invoke(app, ["search", "python", "--index", str(tmp_path / "missing.bin")])
    assert result.exit_code != 0
    assert "Помилка:" in result.output
    assert "Traceback" not in result.output

def test_cli_stats(tiny_corpus, tmp_path):
    index_path = tmp_path / "index.bin"
    runner.invoke(app, ["index", str(tiny_corpus), "--out", str(index_path)])
    result = runner.invoke(app, ["stats", "--index", str(index_path)])
    assert result.exit_code == 0
    assert "Документів" in result.output

@given(st.lists(st.text(alphabet="abcXYZ012", min_size=1, max_size=8), min_size=1, max_size=20, unique=True))
def test_hypothesis_postings_sorted(doc_ids, tmp_path):
    corpus = tmp_path / "posting-corpus"
    corpus.mkdir()
    for number, doc_id in enumerate(doc_ids):
        (corpus / f"{number:03d}_{doc_id}.txt").write_text("shared token", encoding="utf-8")
    built = build_index(corpus)
    for postings in built.values():
        ids = [posting.doc_id for posting in postings]
        assert ids == sorted(ids)

@given(st.sets(st.text(min_size=1, max_size=5)), st.sets(st.text(min_size=1, max_size=5)))
def test_hypothesis_merge_matches_set_operations(left, right):
    from findex.query import _merge_sorted
    assert _merge_sorted(left, right) == left & right
    assert _merge_sorted(left, right, union=True) == left | right

def test_hypothesis_load_save_same_index(tiny_index, tmp_path):
    path = tmp_path / "roundtrip.json"
    save_index(tiny_index, path, "json")
    restored = load_index(path)
    assert dict(restored) == dict(tiny_index)
    assert restored.documents == tiny_index.documents

@given(st.lists(st.text(alphabet="abcдеії", min_size=1, max_size=20), min_size=1, max_size=5))
def test_hypothesis_index_save_load_roundtrip(tmp_path, documents):
    corpus = tmp_path / "generated"
    corpus.mkdir(exist_ok=True)
    for number, content in enumerate(documents):
        (corpus / f"doc_{number}.txt").write_text(content, encoding="utf-8")
    original = build_index(corpus)
    path = tmp_path / "generated.json"
    save_index(original, path, "json")
    restored = load_index(path)
    assert dict(restored) == dict(original)
    assert restored.documents == original.documents


def test_index_mapping_iteration(tiny_index):
    assert set(iter(tiny_index)) == set(tiny_index.keys())

def test_index_document_lengths_positive(tiny_index):
    assert all(meta.length > 0 for meta in tiny_index.documents.values())

def test_tokenizer_generator_is_lazy():
    tokens = tokenize("one two three")
    assert iter(tokens) is tokens

def test_phrase_query_finds_adjacent_terms(tiny_index):
    assert parse('"async await"').evaluate(tiny_index) == {"a.txt"}

def test_boolean_precedence_is_and_before_or():
    assert parse("a OR b c") == Or(Term("a"), And(Term("b"), Term("c")))

def test_snippet_empty_text():
    from findex.ranking import make_snippet
    assert make_snippet("", {"python"}) == ""

def test_scorer_protocol_structural_use(tiny_index):
    for scorer in (BM25(), TfIdf()):
        posting = tiny_index["python"][0]
        assert isinstance(scorer("python", posting, tiny_index), float)


@pytest.mark.parametrize("scorer", [BM25(), TfIdf()])
def test_scorer_prefers_rare_term(tiny_index, scorer):
    rare = tiny_index["async"][0]
    common = tiny_index["python"][0]
    assert scorer("async", rare, tiny_index) > scorer("python", common, tiny_index)


@pytest.mark.parametrize("scorer", [BM25(), TfIdf()])
def test_scorer_returns_finite_nonnegative_scores(tiny_index, scorer):
    import math
    for term, postings in tiny_index.items():
        for posting in postings:
            score = scorer(term, posting, tiny_index)
            assert math.isfinite(score) and score >= 0


def test_bm25_length_normalization_prefers_shorter_document(tiny_index):
    scorer = BM25()
    postings = {posting.doc_id: posting for posting in tiny_index["café"]}
    short = postings["a.txt"] if tiny_index.doc_length("a.txt") < tiny_index.doc_length("c.txt") else postings["c.txt"]
    long = postings["c.txt"] if short.doc_id == "a.txt" else postings["a.txt"]
    assert scorer("café", short, tiny_index) > scorer("café", long, tiny_index)
