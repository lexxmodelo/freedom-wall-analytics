"""Tests for label validators in labeling.py."""
from __future__ import annotations

import pytest

from topic_modeling.labeling import (has_non_ascii, is_lazy_label,
                                     looks_taglish,
                                     strip_wrapping_quotes,
                                     truncate_to_n_words)


@pytest.mark.parametrize("label,expected", [
    ("General", True),
    ("Various Topics", True),
    ("miscellaneous", True),
    ("Topic 5", True),
    ("Noise", True),
    ("General discussion", True),
    ("Other Topics", True),
    ("Academic Stress During Finals", False),
    ("Enrollment Complaints", False),
    ("Cafeteria Food Quality", False),
    ("", True),
    ("   ", True),
])
def test_is_lazy_label(label, expected):
    assert is_lazy_label(label) is expected


@pytest.mark.parametrize("label,expected", [
    ("Academic Stress", False),
    ("Sobrang hirap ng finals", False),     # plain ASCII; should fail looks_taglish, not has_non_ascii
    ("Café", True),
    ("Smart “Quotes”", True),
    ("normal english 123", False),
])
def test_has_non_ascii(label, expected):
    assert has_non_ascii(label) is expected


@pytest.mark.parametrize("label,expected", [
    ("Academic Stress", False),
    ("Cafeteria Food Quality", False),
    ("Sobrang hirap ng finals", True),     # ASCII Taglish — caught by token check
    ("Mahal ko ang school", True),
    ("Para sa enrollment", True),
    ("Ng exam stress", True),
    ("Enrollment Complaints", False),
    ("", False),
])
def test_looks_taglish(label, expected):
    assert looks_taglish(label) is expected


@pytest.mark.parametrize("inp,exp_label,exp_stripped", [
    ('"Academic Stress"', "Academic Stress", True),
    ("'Cafeteria Food'", "Cafeteria Food", True),
    ('“Smart Quote”', "Smart Quote", True),
    ("Already clean", "Already clean", False),
    ('""nested""', "nested", True),
])
def test_strip_wrapping_quotes(inp, exp_label, exp_stripped):
    out, stripped = strip_wrapping_quotes(inp)
    assert out == exp_label
    assert stripped is exp_stripped


@pytest.mark.parametrize("inp,n,exp_label,exp_truncated", [
    ("one two three four five", 5, "one two three four five", False),
    ("one two three four five six", 5, "one two three four five", True),
    ("one two", 5, "one two", False),
])
def test_truncate_to_n_words(inp, n, exp_label, exp_truncated):
    out, truncated = truncate_to_n_words(inp, n)
    assert out == exp_label
    assert truncated is exp_truncated
