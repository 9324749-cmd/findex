"""Ліниве читання текстових документів."""
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterator

@dataclass(frozen=True, slots=True)
class Document:
    doc_id: str
    path: str
    text: str

def iter_documents(root: str | Path) -> Iterator[Document]:
    base = Path(root)
    if not base.exists():
        raise FileNotFoundError(f"Корпус не знайдено: {base}. Спочатку створіть data/.")
    for path in sorted(p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in {".txt", ".md"}):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        yield Document(path.relative_to(base).as_posix(), str(path), text)
