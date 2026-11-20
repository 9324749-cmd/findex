"""Побудова індексу, Python Mapping API та контекстне відкриття."""
from __future__ import annotations
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
import multiprocessing
from typing import Literal
from contextlib import contextmanager
from functools import cached_property
from pathlib import Path
import json, pickle, time, logging
from .corpus import Document, iter_documents
from .models import DocMeta, Posting
from .tokenize import tokenize_with_positions
from .decorators import timed

log = logging.getLogger(__name__)

class Index(Mapping[str, tuple[Posting, ...]]):
    def __init__(self, postings: dict[str, tuple[Posting, ...]], documents: dict[str, DocMeta], texts: dict[str, str] | None = None) -> None:
        self._postings = {term: tuple(items) for term, items in postings.items()}
        self.documents = dict(documents)
        self.texts = dict(texts or {})
        self._closed = False

    def __getitem__(self, term: str) -> tuple[Posting, ...]:
        return self._postings[term]

    def __iter__(self) -> Iterator[str]:
        return iter(self._postings)

    def __len__(self) -> int:
        return len(self._postings)

    def __contains__(self, term: object) -> bool:
        return term in self._postings

    def __repr__(self) -> str:
        return f"Index(terms={len(self)}, docs={self.num_docs})"

    @property
    def num_docs(self) -> int:
        return len(self.documents)

    @cached_property
    def avg_doc_length(self) -> float:
        if not self.documents:
            return 0.0
        return sum(meta.length for meta in self.documents.values()) / self.num_docs

    def doc_length(self, doc_id: str) -> int:
        return self.documents[doc_id].length

    def df(self, term: str) -> int:
        return len(self._postings.get(term, ()))

    def close(self) -> None:
        """Звільняє пам’ять індексу та робить об’єкт закритим."""
        if not self._closed:
            self._postings.clear()
            self.documents.clear()
            self.texts.clear()
            self.__dict__.pop("avg_doc_length", None)
            self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed

def _index_documents(documents_iter: Iterable[Document], *, store_positions: bool = True) -> Index:
    """Build an index from an iterable of Document-like objects."""
    posting_build: dict[str, list[Posting]] = defaultdict(list)
    documents: dict[str, DocMeta] = {}
    texts: dict[str, str] = {}
    for doc in documents_iter:
        doc_id = doc.doc_id
        text = doc.text
        doc_path = doc.path
        pairs = list(tokenize_with_positions(text))
        counts = Counter(token for token, _ in pairs)
        positions: dict[str, list[int]] = defaultdict(list)
        if store_positions:
            for token, pos in pairs:
                positions[token].append(pos)
        title = Path(doc_id).stem.replace("_", " ").replace("-", " ")
        documents[doc_id] = DocMeta(doc_id, doc_path, title, len(pairs))
        texts[doc_id] = text
        for term, tf in counts.items():
            posting_build[term].append(Posting(doc_id, tf, tuple(positions[term]) if store_positions else ()))
    postings = {term: tuple(sorted(items, key=lambda posting: posting.doc_id)) for term, items in posting_build.items()}
    return Index(postings, documents, texts)


def build_partial(paths: list[str], corpus_root: str, store_positions: bool = True) -> Index:
    """Module-level worker: read only the supplied paths and build one partial index.

    Paths, rather than pre-read document texts, cross the executor boundary. This
    keeps task arguments small and makes the function safe for multiprocessing spawn.
    """
    root = Path(corpus_root)
    def read_documents() -> Iterator[Document]:
        for raw_path in paths:
            path = Path(raw_path)
            if path.suffix.lower() == ".jsonl":
                with path.open(encoding="utf-8") as stream:
                    for line_number, line in enumerate(stream, 1):
                        if not line.strip():
                            continue
                        record = json.loads(line)
                        yield Document(str(record.get("url") or f"{path.name}:{line_number}"), str(path), str(record.get("text", "")))
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="utf-8", errors="replace")
            yield Document(path.relative_to(root).as_posix(), str(path), content)
    return _index_documents(read_documents(), store_positions=store_positions)


def merge(partials: Iterable[Index]) -> Index:
    """Merge partial indexes; duplicate document IDs are rejected, never overwritten."""
    postings: dict[str, list[Posting]] = defaultdict(list)
    documents: dict[str, DocMeta] = {}
    texts: dict[str, str] = {}
    for partial in partials:
        overlap = documents.keys() & partial.documents.keys()
        if overlap:
            raise ValueError(f"Повторні doc_id під час merge: {sorted(overlap)[:3]}")
        documents.update(partial.documents)
        texts.update(partial.texts)
        for term, items in partial.items():
            postings[term].extend(items)
    merged = {term: tuple(sorted(items, key=lambda posting: posting.doc_id)) for term, items in postings.items()}
    return Index(merged, documents, texts)


@timed
def build_index(
    corpus_dir: str | Path,
    *,
    store_positions: bool = True,
    workers: int = 1,
    executor: Literal["serial", "threads", "processes"] = "serial",
) -> Index:
    """Build the same index serially, with threads, or with worker processes."""
    root = Path(corpus_dir)
    if not root.exists():
        raise FileNotFoundError(f"Корпус не знайдено: {root}")
    if workers < 1:
        raise ValueError("workers має бути не менше 1")
    if executor not in {"serial", "threads", "processes"}:
        raise ValueError("executor має бути serial, threads або processes")
    paths = sorted(str(path) for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".txt", ".md", ".jsonl"})
    if not paths:
        return Index({}, {}, {})
    if executor == "serial":
        return merge([build_partial(paths, str(root), store_positions)])
    chunk_size = (len(paths) + workers - 1) // workers
    chunks = [paths[i:i + chunk_size] for i in range(0, len(paths), chunk_size)]
    pool_type = ThreadPoolExecutor if executor == "threads" else ProcessPoolExecutor
    # Exceptions from a worker are re-raised by future.result(); executor shutdown
    # waits for remaining tasks and no silent partial index is returned.
    pool_options = {"mp_context": multiprocessing.get_context("spawn")} if executor == "processes" else {}
    with pool_type(max_workers=workers, **pool_options) as pool:
        futures = [pool.submit(build_partial, chunk, str(root), store_positions) for chunk in chunks]
        partials = [future.result() for future in futures]
    return merge(partials)

def save_index(index: Index, path: str | Path, fmt: Literal["pickle", "pkl", "bin", "json"] | None = None) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fmt = (fmt or target.suffix.lstrip(".") or "pickle").lower()
    payload = {"postings": {t: [{"doc_id": p.doc_id, "tf": p.tf, "positions": list(p.positions)} for p in ps] for t, ps in index.items()},
               "documents": {k: {"doc_id": v.doc_id, "path": v.path, "title": v.title, "length": v.length} for k, v in index.documents.items()},
               "texts": index.texts}
    if fmt in {"pickle", "pkl", "bin"}:
        with target.open("wb") as f: pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    elif fmt == "json":
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    else:
        raise ValueError("Формат має бути pickle або json")
    return target

@timed
def load_index(path: str | Path) -> Index:
    target = Path(path)
    if target.suffix.lower() == ".json":
        payload = json.loads(target.read_text(encoding="utf-8"))
    else:
        # Завантажуйте pickle лише з довірених джерел: pickle не є безпечним форматом для чужих файлів.
        with target.open("rb") as f:
            payload = pickle.load(f)
    postings = {t: tuple(Posting(p["doc_id"], int(p["tf"]), tuple(p.get("positions", ()))) for p in ps) for t, ps in payload["postings"].items()}
    documents = {k: DocMeta(**v) for k, v in payload["documents"].items()}
    index = Index(postings, documents, payload.get("texts", {}))
    return index

@contextmanager
def open_index(path: str | Path) -> Iterator[Index]:
    index = load_index(path)
    try:
        yield index
    finally:
        index.close()


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Побудова інвертованого індексу findex")
    parser.add_argument("corpus", nargs="?", default="data/")
    parser.add_argument("--out", default="index.bin")
    parser.add_argument("--format", choices=["pickle", "json"], default="pickle")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    index = build_index(args.corpus)
    save_index(index, args.out, args.format)
    log.info("Побудовано індекс: %s", index)

if __name__ == "__main__":
    main()
