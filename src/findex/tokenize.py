from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator

_TOKEN_PATTERN = re.compile(
    r"[^\W_]+(?:['’ʼ-][^\W_]+)*",
    flags=re.UNICODE,
)


def tokenize(text: str) -> Iterator[str]:
    """Yield normalized Unicode words, numbers, internal apostrophes and hyphens."""
    normalized = unicodedata.normalize("NFC", text).casefold()
    for match in _TOKEN_PATTERN.finditer(normalized):
        yield match.group(0)
