"""One-pass lazy corpus statistics and eager-vs-lazy benchmark."""

from __future__ import annotations

import argparse
from collections import Counter
from itertools import islice
from pathlib import Path
import time
import tracemalloc

from findex.corpus import Document, iter_documents
from findex.tokenize import tokenize


def collect_lazy(root: Path, limit: int | None = None) -> dict:
    """Count corpus statistics while retaining only one document at a time."""
    documents = iter_documents(root)
    if limit is not None:
        documents = islice(documents, limit)

    doc_count = 0
    token_count = 0
    terms: Counter[str] = Counter()

    for document in documents:
        doc_count += 1
        for token in tokenize(document.text):
            token_count += 1
            terms[token] += 1

    return {
        "documents": doc_count,
        "tokens": token_count,
        "vocabulary": len(terms),
        "top_terms": terms.most_common(50),
    }


def collect_eager(root: Path, limit: int | None = None) -> dict:
    """Intentionally memory-hungry implementation used only for comparison."""
    documents = list(iter_documents(root))
    if limit is not None:
        documents = documents[:limit]

    token_lists = [list(tokenize(document.text)) for document in documents]
    all_tokens = [token for tokens in token_lists for token in tokens]
    terms = Counter(all_tokens)

    return {
        "documents": len(documents),
        "tokens": len(all_tokens),
        "vocabulary": len(terms),
        "top_terms": terms.most_common(50),
    }


def measure(function, root: Path, limit: int | None = None) -> tuple[dict, float, int]:
    """Return result, elapsed seconds, and peak traced Python memory in bytes."""
    tracemalloc.start()
    started = time.perf_counter()
    try:
        result = function(root, limit)
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, elapsed, peak


def format_bytes(value: int) -> str:
    return f"{value / (1024 * 1024):.2f} MiB"


def main() -> None:
    parser = argparse.ArgumentParser(description="Stream a text corpus and count terms.")
    parser.add_argument("root", nargs="?", type=Path, default=Path("data"))
    parser.add_argument("--limit", type=int, default=None, help="process only first N documents")
    parser.add_argument(
        "--compare", action="store_true",
        help="also run the eager list-based implementation (uses more memory)",
    )
    args = parser.parse_args()

    lazy, lazy_time, lazy_peak = measure(collect_lazy, args.root, args.limit)
    print("FINDEX — LAZY STATISTICS")
    print(f"Documents: {lazy['documents']}")
    print(f"Tokens: {lazy['tokens']}")
    print(f"Vocabulary: {lazy['vocabulary']}")
    print("Top terms:")
    for term, count in lazy["top_terms"]:
        print(f"  {term}: {count}")
    print(f"Elapsed: {lazy_time:.4f} s")
    print(f"Peak traced memory: {format_bytes(lazy_peak)}")

    if args.compare:
        eager, eager_time, eager_peak = measure(collect_eager, args.root, args.limit)
        print("\nEAGER VS LAZY")
        print(f"{'Version':<12} {'Documents':>10} {'Peak memory':>14} {'Elapsed':>12}")
        print("-" * 52)
        print(f"{'eager':<12} {eager['documents']:>10} {format_bytes(eager_peak):>14} {eager_time:>11.4f}s")
        print(f"{'lazy':<12} {lazy['documents']:>10} {format_bytes(lazy_peak):>14} {lazy_time:>11.4f}s")
        if eager["tokens"] != lazy["tokens"] or eager["top_terms"] != lazy["top_terms"]:
            raise RuntimeError("Eager and lazy implementations produced different results.")


if __name__ == "__main__":
    main()
