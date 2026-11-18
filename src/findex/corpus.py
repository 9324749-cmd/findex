from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True, slots=True)
class Document:
    doc_id: int
    path: str
    text: str


def iter_documents(root: str | Path) -> Iterator[Document]:
    """Yield UTF-8 text files one at a time in stable path order."""
    base = Path(root)
    for doc_id, path in enumerate(sorted(base.rglob("*.txt")), start=1):
        if not path.is_file():
            continue
        yield Document(doc_id=doc_id, path=str(path), text=path.read_text(
            encoding="utf-8", errors="replace"
        ))
