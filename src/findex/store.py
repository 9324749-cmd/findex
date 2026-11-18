"""Persistence for findex indexes: trusted-local pickle and portable JSON."""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Literal

from findex.models import DocMeta, IndexData, Posting

Format = Literal["pickle", "json"]


def _to_payload(index: IndexData) -> dict:
    return {
        "postings": {
            term: [
                {"doc_id": p.doc_id, "tf": p.tf, "positions": list(p.positions)}
                for p in items
            ]
            for term, items in index.postings.items()
        },
        "doc_lengths": {str(k): v for k, v in index.doc_lengths.items()},
        "doc_meta": {
            str(k): {"doc_id": v.doc_id, "path": v.path, "title": v.title}
            for k, v in index.doc_meta.items()
        },
        "positions_enabled": index.positions_enabled,
    }


def _from_payload(data: dict) -> IndexData:
    postings = {
        term: [
            Posting(int(p["doc_id"]), int(p["tf"]), tuple(int(x) for x in p.get("positions", [])))
            for p in items
        ]
        for term, items in data["postings"].items()
    }
    doc_lengths = {int(k): int(v) for k, v in data["doc_lengths"].items()}
    doc_meta = {
        int(k): DocMeta(int(v["doc_id"]), str(v["path"]), str(v["title"]))
        for k, v in data["doc_meta"].items()
    }
    return IndexData(postings, doc_lengths, doc_meta, bool(data.get("positions_enabled", False)))


def save_index(index: IndexData, path: str | Path, *, fmt: Format = "pickle") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "pickle":
        # SECURITY: pickle.load can execute arbitrary code. Only load files you created
        # yourself; never load a pickle downloaded from an unknown person or website.
        with target.open("wb") as stream:
            pickle.dump(index, stream, protocol=pickle.HIGHEST_PROTOCOL)
    elif fmt == "json":
        target.write_text(
            json.dumps(_to_payload(index), ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
    else:
        raise ValueError(f"Unsupported format: {fmt}")


def load_index(path: str | Path, *, fmt: Format | None = None) -> IndexData:
    target = Path(path)
    actual = fmt or ("json" if target.suffix.lower() == ".json" else "pickle")
    if actual == "pickle":
        # SECURITY: see save_index above. Never unpickle untrusted files.
        with target.open("rb") as stream:
            result = pickle.load(stream)
        if not isinstance(result, IndexData):
            raise TypeError("The pickle file does not contain a findex IndexData object")
        return result
    if actual == "json":
        return _from_payload(json.loads(target.read_text(encoding="utf-8")))
    raise ValueError(f"Unsupported format: {actual}")
