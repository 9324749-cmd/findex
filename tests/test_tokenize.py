from findex.tokenize import tokenize


def test_mixed_case_is_casefolded():
    assert list(tokenize("PyThOn PYTHON")) == ["python", "python"]


def test_cyrillic_and_ukrainian_text():
    assert list(tokenize("Київ — Україна")) == ["київ", "україна"]


def test_combining_mark_is_nfc_normalized():
    assert list(tokenize("cafe\u0301")) == ["café"]


def test_punctuation_is_a_separator():
    assert list(tokenize("Привіт, світе!")) == ["привіт", "світе"]


def test_empty_string_has_no_tokens():
    assert list(tokenize("")) == []


def test_internal_apostrophes_are_preserved():
    assert list(tokenize("п'ять don't")) == ["п'ять", "don't"]


def test_internal_hyphen_is_preserved():
    assert list(tokenize("будь-який")) == ["будь-який"]


def test_digits_are_kept():
    assert list(tokenize("Python 3.12 та 2026")) == ["python", "3", "12", "та", "2026"]


def test_underscore_is_separator():
    assert list(tokenize("findex_search")) == ["findex", "search"]
