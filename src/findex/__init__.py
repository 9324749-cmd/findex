"""Навчальна пошукова система findex з лінивим імпортом публічного API."""
__all__ = ["DocMeta", "Posting", "Index", "build_index", "open_index", "BM25", "TfIdf", "SearchResult", "search"]

def __getattr__(name):
    if name in {"DocMeta", "Posting"}:
        from . import models
        return getattr(models, name)
    if name in {"Index", "build_index", "open_index"}:
        from . import index
        return getattr(index, name)
    if name in {"BM25", "TfIdf", "SearchResult", "search"}:
        from . import ranking
        return getattr(ranking, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
