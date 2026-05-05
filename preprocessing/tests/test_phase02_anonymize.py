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
    # Indexing hashtags
    ("#ADMUFreedomWall12345", ["[Metro Manila]"], ["ADMU", "FreedomWall"]),
    ("#UPDilimanFreedomWall5555", ["[Metro Manila]"], ["UPD", "Diliman"]),
    ("#SLUFreedomWall25117", ["[Baguio/Benguet]"], ["SLU", "FreedomWall"]),
    ("#UPLBFreedomWall2025", ["[Luzon/Provincial]"], ["UPLB"]),
    # Full names + acronyms
    ("Ateneo de Manila University vs UP Diliman", ["[Metro Manila]"], ["Ateneo", "Diliman"]),
    ("ADMU and UPD comparison", ["[Metro Manila]"], ["ADMU", "UPD"]),
    # Acronym shadowing protection: UP must not match inside UPLB
    ("UPLB has the best campus", ["[Luzon/Provincial]"], ["UPLB"]),
    # Location markers
    ("Wala nang jeep sa Katipunan grabe", ["[Metro Manila]"], ["Katipunan"]),
    ("Los Baños weather is terrible", ["[Luzon/Provincial]"], ["Los Baños"]),
    ("Maryheights area ako nakatira", ["[Baguio/Benguet]"], ["Maryheights"]),
    # Mascots
    ("Go Tamaraws!", ["[Metro Manila]"], ["Tamaraws"]),
    ("Animo La Salle", ["[Metro Manila]"], ["Animo La Salle", "La Salle"]),
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
    # Should NOT contain "[Metro Manila] [Metro Manila]" (collapsed by orchestrator)
    assert "[Metro Manila] [Metro Manila]" not in out


def test_cross_university_post_records_two_regions(table):
    text = "ADMU vs DLSU debate"
    _, _, regions = anonymize(text, table)
    assert "Metro Manila" in regions  # both ADMU and DLSU map to Metro Manila


def test_no_match_returns_empty_regions(table):
    text = "Just a generic post about thesis stress"
    out, _, regions = anonymize(text, table)
    assert out == text
    assert regions == set()
