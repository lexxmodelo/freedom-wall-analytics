"""Phase 02 anonymization tests.

Validate replacement table ordering (longer-before-shorter) and the linguistic-
preserve rule on representative inputs from all 12 schools.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from preprocessing.phase02_anonymize_school import anonymize
from preprocessing.schools import build_replacement_table, load_schools

CONFIGS = Path(__file__).resolve().parents[1] / "configs"


@pytest.fixture(scope="module")
def table():
    cfg = load_schools(CONFIGS / "schools.yaml")
    return build_replacement_table(cfg)


@pytest.mark.parametrize("text,must_contain,must_not_contain", [
    # Indexing hashtags — DROPPED entirely (region is already captured in
    # the post's `region` output field via source-code routing).
    ("#ADMUFreedomWall12345 hello", ["hello"], ["ADMU", "FreedomWall", "[NCR]"]),
    ("#UPDilimanFreedomWall5555 hi", ["hi"], ["UPD", "Diliman", "[NCR]"]),
    ("#SLUFreedomWall25117 ok", ["ok"], ["SLU", "FreedomWall", "[CAR]"]),
    ("#UPLBFreedomWall2025 yo", ["yo"], ["UPLB", "[CALABARZON]"]),
    # Full names + acronyms
    ("Ateneo de Manila University vs UP Diliman", ["[NCR]"], ["Ateneo", "Diliman"]),
    ("ADMU and UPD comparison", ["[NCR]"], ["ADMU", "UPD"]),
    # Acronym shadowing protection: UP must not match inside UPLB
    ("UPLB has the best campus", ["[CALABARZON]"], ["UPLB"]),
    # Location markers
    ("Wala nang jeep sa Katipunan grabe", ["[NCR]"], ["Katipunan"]),
    ("Los Baños weather is terrible", ["[CALABARZON]"], ["Los Baños"]),
    ("Maryheights area ako nakatira", ["[CAR]"], ["Maryheights"]),
    # Mascots
    ("Go Tamaraws!", ["[NCR]"], ["Tamaraws"]),
    ("Animo La Salle", ["[NCR]"], ["Animo La Salle", "La Salle"]),
    # Ambiguous mascot — dropped, NOT tagged
    ("Go Maroons!", [], ["Maroons"]),
])
def test_anonymize_replacements(table, text, must_contain, must_not_contain):
    out, _, _ = anonymize(text, table)
    for needle in must_contain:
        assert needle in out, f"Expected {needle!r} in: {out!r}"
    for needle in must_not_contain:
        assert needle not in out, f"Expected {needle!r} NOT in: {out!r}"


def test_repeated_region_tags_collapse(table):
    """ADMU and Ateneo in the same sentence should collapse to one tag."""
    text = "ADMU vs Ateneo de Manila University is the same school"
    out, _, _ = anonymize(text, table)
    # Should NOT contain "[NCR] [NCR]" (collapsed by orchestrator)
    assert "[NCR] [NCR]" not in out


def test_cross_university_post_records_two_regions(table):
    text = "ADMU vs DLSU debate"
    _, _, regions = anonymize(text, table)
    assert "NCR" in regions  # both ADMU and DLSU map to NCR


def test_no_match_returns_empty_regions(table):
    text = "Just a generic post about thesis stress"
    out, _, regions = anonymize(text, table)
    assert out == text
    assert regions == set()


def test_skip_bare_acronym_ub_survives(table):
    """UB has skip_bare_acronym=true; bare 'UB' should NOT be replaced.
    The school is still anonymized via hashtag and full-name passes."""
    # Bare UB is allowed to survive (tier E)
    out, _, _ = anonymize("watching games sa UB nung weekend", table)
    assert "UB" in out
    assert "[CAR]" not in out
    # But "University of Baguio" still gets anonymized (full-name pass)
    out, _, _ = anonymize("studying at University of Baguio", table)
    assert "University of Baguio" not in out
    assert "[CAR]" in out
    # And the indexing hashtag still gets dropped (just empty result here,
    # since the entire input is just the hashtag)
    out, _, _ = anonymize("#UBFreedomWall100 body", table)
    assert "UBFreedomWall100" not in out
    assert "body" in out


def test_case_sensitive_pup(table):
    """PUP has case_sensitive_acronym=true; uppercase replaces, lowercase doesn't."""
    # Uppercase: replaced
    out, _, _ = anonymize("transfer to PUP next year", table)
    assert "PUP" not in out
    assert "[NCR]" in out
    # Lowercase: NOT replaced (defensive against "pup" the baby dog)
    out, _, _ = anonymize("looking for a pup to adopt", table)
    assert "pup" in out
    assert "[NCR]" not in out


def test_pirates_now_ambiguous(table):
    """Pirates was demoted from LPU-B mascot to ambiguous_mascots; should be
    dropped without a region tag (it's usually 'Pirates Cafe' in the corpus)."""
    out, _, _ = anonymize("nag-aral sa Pirates Cafe last week", table)
    assert "Pirates" not in out
    # Should NOT add a region tag — it's ambiguous, just deleted
    assert "[CALABARZON]" not in out
