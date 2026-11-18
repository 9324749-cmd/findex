"""Unicode-aware streaming tokenizer."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator

# A token starts and ends with a Unicode letter/number. Internal apostrophes
# and hyphens are accepted only when surrounded by letters/numbers.
_TOKEN_PATTERN = re.compile(r"[^\W_]+(?:[’'ʼ-][^\W_]+)*", flags=re.UNICODE)


def tokenize(text: str) -> Iterator[str]:
    """Yield normalized tokens without constructing a list of all matches.

    Rules:
    - NFC normalization combines canonically equivalent Unicode sequences.
    - casefold() makes matching case-insensitive beyond simple lowercasing.
    - Letters and digits are retained; underscores are separators.
    - Internal straight/curly/Ukrainian apostrophes and hyphens stay inside
      a token when surrounded by letters or digits (e.g. п'ять, будь-який).
    - Leading/trailing punctuation and standalone symbols are discarded.
    """
    normalized = unicodedata.normalize("NFC", text).casefold()
    for match in _TOKEN_PATTERN.finditer(normalized):
        yield match.group(0)
