"""Data models used by the inverted index."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, order=True)
class Posting:
    """One term occurrence summary for a document."""

    doc_id: int
    tf: int
    positions: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class DocMeta:
    """Small display metadata for one indexed document."""

    doc_id: int
    path: str
    title: str


@dataclass(slots=True)
class IndexData:
    """Complete in-memory inverted index."""

    postings: dict[str, list[Posting]]
    doc_lengths: dict[int, int]
    doc_meta: dict[int, DocMeta]
    positions_enabled: bool = False
