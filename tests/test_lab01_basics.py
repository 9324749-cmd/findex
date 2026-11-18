from findex.tokenize import tokenize


def test_unicode_and_casefold():
    assert list(tokenize("ПРИВІТ Straße")) == ["привіт", "strasse"]


def test_apostrophe_hyphen_digits():
    assert list(tokenize("п'ять будь-який Python 3.12")) == [
        "п'ять", "будь-який", "python", "3", "12"
    ]


def test_empty_text():
    assert list(tokenize("")) == []
