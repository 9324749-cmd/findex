"""Незмінні моделі даних інвертованого індексу."""
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Posting:
    doc_id: str
    tf: int
    positions: tuple[int, ...] = ()

@dataclass(frozen=True, slots=True)
class DocMeta:
    doc_id: str
    path: str
    title: str
    length: int
