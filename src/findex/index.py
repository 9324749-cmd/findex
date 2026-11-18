"""Build and persist an inverted index from the Lab 1 lazy corpus pipeline."""
from __future__ import annotations

import argparse
import time
import tracemalloc
from collections import Counter, defaultdict
from pathlib import Path

from findex.corpus import iter_documents
from findex.tokenize import tokenize
from findex.models import DocMeta, IndexData, Posting
from findex.store import save_index


def _numeric_doc_id(raw_id: object, fallback: int) -> int:
    """Use a numeric Lab 1 ID when available; otherwise use stream order."""
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return fallback


def build_index(root: str | Path, *, positions: bool = False) -> IndexData:
    """Build postings in one pass; only the current document is token-buffered."""
    postings: defaultdict[str, list[Posting]] = defaultdict(list)
    doc_lengths: dict[int, int] = {}
    doc_meta: dict[int, DocMeta] = {}

    for ordinal, document in enumerate(iter_documents(root), start=1):
        doc_id = _numeric_doc_id(getattr(document, "doc_id", ordinal), ordinal)
        path = str(getattr(document, "path", ""))
        title = Path(path).stem if path else f"Document {doc_id}"
        counts: Counter[str] = Counter()
        token_positions: defaultdict[str, list[int]] = defaultdict(list)

        for offset, term in enumerate(tokenize(document.text)):
            counts[term] += 1
            if positions:
                token_positions[term].append(offset)

        doc_lengths[doc_id] = sum(counts.values())
        doc_meta[doc_id] = DocMeta(doc_id=doc_id, path=path, title=title)

        for term, tf in counts.items():
            term_positions = tuple(token_positions[term]) if positions else ()
            postings[term].append(Posting(doc_id=doc_id, tf=tf, positions=term_positions))

    # The stream may not have arrived in ID order; enforce the required ordering.
    sorted_postings = {
        term: sorted(items, key=lambda item: item.doc_id)
        for term, items in postings.items()
    }
    return IndexData(
        postings=sorted_postings,
        doc_lengths=doc_lengths,
        doc_meta=doc_meta,
        positions_enabled=positions,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and save the findex inverted index.")
    parser.add_argument("corpus", help="Path to the Lab 1 data/ corpus")
    parser.add_argument("--out", default="index.bin", help="Output index file")
    parser.add_argument("--format", choices=("pickle", "json"), default=None,
                        help="Storage format (default: inferred from .json suffix or pickle)")
    parser.add_argument("--positions", action="store_true",
                        help="Store token offsets for optional phrase-search work")
    args = parser.parse_args()

    fmt = args.format or ("json" if Path(args.out).suffix.lower() == ".json" else "pickle")

    tracemalloc.start()
    started = time.perf_counter()
    index = build_index(args.corpus, positions=args.positions)
    build_seconds = time.perf_counter() - started
    _, build_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    save_started = time.perf_counter()
    save_index(index, args.out, fmt=fmt)
    save_seconds = time.perf_counter() - save_started
    size = Path(args.out).stat().st_size

    print(f"Documents: {len(index.doc_meta)}")
    print(f"Terms: {len(index.postings)}")
    print(f"Build time: {build_seconds:.6f} s")
    print(f"Build peak memory: {build_peak / 1024 / 1024:.3f} MiB")
    print(f"Save time ({fmt}): {save_seconds:.6f} s")
    print(f"File size: {size / 1024:.2f} KiB")
    print(f"Saved to: {args.out}")


if __name__ == "__main__":
    main()
