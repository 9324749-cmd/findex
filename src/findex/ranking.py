"""TF-IDF/BM25 ранжування, кеш запитів і снипети."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from functools import lru_cache
from collections import OrderedDict
from heapq import nlargest
from math import log, log1p
from collections import Counter
import re, logging
from .decorators import timed
from .query import parse
from .tokenize import tokenize

class Scorer(Protocol):
    def __call__(self, term: str, posting, index) -> float: ...

class TfIdf:
    def __call__(self, term, posting, index):
        tf = posting.tf
        idf = log((index.num_docs + 1) / (index.df(term) + 1)) + 1.0
        return (1.0 + log(tf)) * idf
    def __repr__(self): return "TfIdf()"

class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        if k1 <= 0 or not 0 <= b <= 1: raise ValueError("Потрібно k1 > 0 та 0 <= b <= 1")
        self.k1, self.b = k1, b
    def __call__(self, term, posting, index):
        n, df, tf = index.num_docs, index.df(term), posting.tf
        if not n: return 0.0
        idf = log(1 + (n - df + 0.5) / (df + 0.5))
        length = index.doc_length(posting.doc_id)
        avg = index.avg_doc_length or 1.0
        norm = tf + self.k1 * (1 - self.b + self.b * length / avg)
        return idf * (tf * (self.k1 + 1)) / norm
    def __repr__(self): return f"BM25(k1={self.k1}, b={self.b})"

@dataclass(order=True, frozen=True, init=False)
class SearchResult:
    # score is first so sorted(results) orders by score; constructor keeps doc_id-first API.
    score: float
    doc_id: str
    title: str
    snippet: str = ""
    def __init__(self, doc_id: str, score: float, title: str, snippet: str = ""):
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "doc_id", doc_id)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "snippet", snippet)
    def __str__(self): return f"{self.title} [{self.doc_id}] score={self.score:.4f}: {self.snippet}"

_INDEX_REGISTRY = OrderedDict()

@lru_cache(maxsize=256)
def _cached_ids(index_id: int, query_text: str, engine: str, signature: tuple) -> frozenset[str]:
    index = _INDEX_REGISTRY[index_id]
    return frozenset(parse(query_text).evaluate(index, engine))

def _matched_ids(index, query_text, engine="set"):
    index_id = id(index)
    _INDEX_REGISTRY[index_id] = index
    _INDEX_REGISTRY.move_to_end(index_id)
    while len(_INDEX_REGISTRY) > 256:
        _INDEX_REGISTRY.popitem(last=False)
    before = _cached_ids.cache_info()
    signature = (len(index.documents), len(index), tuple(sorted(index.documents)))
    result = _cached_ids(index_id, query_text, engine, signature)
    after = _cached_ids.cache_info()
    event = "HIT" if after.hits > before.hits else "MISS"
    logging.getLogger("findex.cache").info("[cache] %s query=%r", event, query_text)
    return set(result)

def make_snippet(text: str, terms: set[str], window: int = 80) -> str:
    if not text: return ""
    normalized = text.casefold()
    matches = [m.start() for term in terms if term for m in re.finditer(re.escape(term), normalized)]
    # Обираємо найраніше входження серед термів запиту як стабільний центр сніпета.
    center = min(matches) if matches else 0
    start, end = max(0, center-window), min(len(text), center+window)
    snippet = text[start:end].replace("\n", " ")
    for term in sorted(terms, key=len, reverse=True):
        if term: snippet = re.sub(re.escape(term), lambda m: f"**{m.group(0)}**", snippet, flags=re.IGNORECASE)
    return ("…" if start else "") + snippet + ("…" if end < len(text) else "")

@timed
def search(index, query: str, scorer: Scorer | None = None, k: int = 10, engine: str = "set") -> list[SearchResult]:
    scorer = scorer or BM25()
    matched = _matched_ids(index, query, engine)
    clean_query = re.sub(r"\b(?:AND|OR|NOT)\b", " ", query, flags=re.IGNORECASE)
    terms = set(tokenize(clean_query.replace(chr(34), " ")))
    scores: Counter[str] = Counter()
    for term in terms:
        for posting in index.get(term, ()):
            if posting.doc_id in matched:
                scores[posting.doc_id] += scorer(term, posting, index)
    # Phrase-only results may have zero term scores; keep them visible at the end.
    for doc_id in matched: scores.setdefault(doc_id, 0.0)
    top = nlargest(max(0, k), scores.items(), key=lambda item: (item[1], item[0]))
    results = []
    for doc_id, score in top:
        meta = index.documents[doc_id]
        snippet = make_snippet(index.texts.get(doc_id, ""), terms)
        results.append(SearchResult(doc_id, float(score), meta.title, snippet))
    return results

def cache_info():
    return _cached_ids.cache_info()
