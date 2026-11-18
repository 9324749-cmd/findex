from __future__ import annotations

import argparse
import time
import tracemalloc
from collections import Counter

from findex.corpus import iter_documents
from findex.tokenize import tokenize


def collect_lazy(root):
    counts = Counter()
    documents = tokens = 0
    for document in iter_documents(root):
        documents += 1
        for token in tokenize(document.text):
            counts[token] += 1
            tokens += 1
    return {"documents": documents, "tokens": tokens, "vocabulary": len(counts),
            "top50": counts.most_common(50)}


def collect_eager(root):
    docs = list(iter_documents(root))
    token_lists = [list(tokenize(doc.text)) for doc in docs]
    all_tokens = [token for row in token_lists for token in row]
    counts = Counter(all_tokens)
    return {"documents": len(docs), "tokens": len(all_tokens),
            "vocabulary": len(counts), "top50": counts.most_common(50)}


def measure(function, root):
    tracemalloc.start()
    started = time.perf_counter()
    result = function(root)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, elapsed, peak


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus")
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()
    if args.compare:
        for name, function in (("eager", collect_eager), ("lazy", collect_lazy)):
            result, elapsed, peak = measure(function, args.corpus)
            print(f"{name}: documents={result['documents']} tokens={result['tokens']} "
                  f"vocabulary={result['vocabulary']} time={elapsed:.6f}s "
                  f"peak={peak / 1024 / 1024:.3f}MiB")
    else:
        result, elapsed, peak = measure(collect_lazy, args.corpus)
        print(result)
        print(f"time={elapsed:.6f}s peak={peak / 1024 / 1024:.3f}MiB")


if __name__ == "__main__":
    main()
