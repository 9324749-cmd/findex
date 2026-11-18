"""Measure plain dataclass, slotted dataclass, and compact array postings."""
from __future__ import annotations

import argparse
import pickle
import tempfile
import time
import tracemalloc
from array import array
from dataclasses import dataclass
from pathlib import Path

from findex.index import build_index
from findex.models import Posting


@dataclass(frozen=True)
class PlainPosting:
    doc_id: int
    tf: int


def _flatten(index):
    pairs = []
    for term in sorted(index.postings):
        for posting in index.postings[term]:
            pairs.append((posting.doc_id, posting.tf))
    return pairs


def _measure(factory, label: str, pairs: list[tuple[int, int]]) -> dict[str, object]:
    tracemalloc.start()
    started = time.perf_counter()
    value = factory(pairs)
    build_time = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    with tempfile.TemporaryDirectory() as temp_dir:
        target = Path(temp_dir) / "representation.pkl"
        save_started = time.perf_counter()
        with target.open("wb") as stream:
            pickle.dump(value, stream, protocol=pickle.HIGHEST_PROTOCOL)
        save_time = time.perf_counter() - save_started
        size = target.stat().st_size
        load_started = time.perf_counter()
        with target.open("rb") as stream:
            loaded = pickle.load(stream)
        load_time = time.perf_counter() - load_started
        # Keep the loaded object alive through the measurement.
        _ = loaded

    return {
        "representation": label,
        "peak_mib": peak / 1024 / 1024,
        "build_seconds": build_time,
        "file_kib": size / 1024,
        "save_seconds": save_time,
        "load_seconds": load_time,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure posting storage representations.")
    parser.add_argument("corpus")
    args = parser.parse_args()

    index = build_index(args.corpus)
    pairs = _flatten(index)
    rows = [
        _measure(lambda data: [PlainPosting(doc, tf) for doc, tf in data],
                 "plain dataclass", pairs),
        _measure(lambda data: [Posting(doc, tf) for doc, tf in data],
                 "dataclass slots=True", pairs),
        _measure(lambda data: (array("I", (doc for doc, _ in data)),
                               array("I", (tf for _, tf in data))),
                 "array('I') pairs", pairs),
    ]

    print("| Representation | Peak memory (MiB) | Build (s) | File (KiB) | Save (s) | Load (s) |")
    print("|---|---:|---:|---:|---:|---:|")
    for row in rows:
        print(
            f"| {row['representation']} | {row['peak_mib']:.3f} | "
            f"{row['build_seconds']:.6f} | {row['file_kib']:.2f} | "
            f"{row['save_seconds']:.6f} | {row['load_seconds']:.6f} |"
        )


if __name__ == "__main__":
    main()
