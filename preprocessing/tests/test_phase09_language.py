"""Phase 09 language detection tests."""
from __future__ import annotations

import pytest

from preprocessing.phase09_language import detect


@pytest.mark.parametrize("text,expected", [
    ("The English-only post talking about midterms and exam stress without any Tagalog particles whatsoever in the entire body of the message.", "English"),
    ("Ang hirap talaga ng buhay-estudyante kasi puro deadline at requirements naman lahat dito.", "Filipino"),
    ("Hello po sa mga tiga school! Ask lang if pwede pa ba magchange of course since hindi pala accredited.", "Taglish"),
])
def test_language_classification(text, expected):
    label, _ = detect(text)
    assert label == expected, f"Got {label!r} for: {text!r}"


def test_short_text_returns_unknown():
    label, _ = detect("ok")
    assert label == "Unknown"
