"""Нормалізація й потокова токенізація."""
import re
import unicodedata
from collections.abc import Iterator

_TOKEN_RE = re.compile(r"[^\W_]+(?:['’ʼ-][^\W_]+)*", re.UNICODE)

def tokenize_with_positions(text: str) -> Iterator[tuple[str, int]]:
    normalized = unicodedata.normalize("NFC", text).casefold()
    for position, match in enumerate(_TOKEN_RE.finditer(normalized)):
        yield match.group(0), position

def tokenize(text: str) -> Iterator[str]:
    for token, _ in tokenize_with_positions(text):
        yield token
