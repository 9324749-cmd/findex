"""Lazy readers for a directory tree of UTF-8 text documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Document:
    """One corpus document."""

    doc_id: str
    path: Path
    text: str


def iter_documents(root: Path) -> Iterator[Document]:
    """Yield .txt files one at a time, in stable path order.

    Files are opened individually and closed before the next document is read.
    Invalid UTF-8 bytes are replaced so one damaged file does not stop indexing.
    A missing/non-directory root raises FileNotFoundError or NotADirectoryError.
    """
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(f"Corpus directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Corpus path is not a directory: {root}")

    for path in root.rglob("*.txt"):
        try:
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                text = stream.read()
        except OSError as exc:
            logger.warning("Skipping unreadable file %s: %s", path, exc)
            continue

        yield Document(
            doc_id=path.relative_to(root).as_posix(),
            path=path,
            text=text,
        )
