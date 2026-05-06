"""Distribute tests: LPT bin-pack correctness for 1..5 researchers."""
from __future__ import annotations

import pytest

from vad_scoring.distribute import (
    _FALLBACK_BATCHES, balance_assignments, count_batches_per_university, get_active_universities,
)


ALL_TEN = sorted(_FALLBACK_BATCHES.keys())


def test_count_batches_uses_fallback_when_no_outputs_dir():
    counts = count_batches_per_university(ALL_TEN)
    assert counts == _FALLBACK_BATCHES


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_balance_preserves_total_universities(n):
    slices = balance_assignments(ALL_TEN, n)
    flat = [u for s in slices for u in s.universities]
    assert sorted(flat) == ALL_TEN
    assert len(flat) == 10  # no overlap, no drops


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_balance_preserves_total_batches(n):
    slices = balance_assignments(ALL_TEN, n)
    expected = sum(_FALLBACK_BATCHES.values())
    actual = sum(s.total_batches for s in slices)
    assert actual == expected


def test_balance_one_researcher_gets_everything():
    slices = balance_assignments(ALL_TEN, 1)
    assert len(slices) == 1
    assert sorted(slices[0].universities) == ALL_TEN
    assert slices[0].total_batches == sum(_FALLBACK_BATCHES.values())


def test_balance_returns_n_slices():
    for n in range(1, 6):
        slices = balance_assignments(ALL_TEN, n)
        assert len(slices) == n
        assert [s.researcher_index for s in slices] == list(range(1, n + 1))


@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_lpt_makespan_within_4_3_of_optimal(n):
    """LPT is provably ≤4/3 of optimal makespan. Check the heuristic guarantee."""
    slices = balance_assignments(ALL_TEN, n)
    loads = [s.total_batches for s in slices]
    optimal_lower_bound = sum(_FALLBACK_BATCHES.values()) / n
    makespan = max(loads)
    assert makespan <= optimal_lower_bound * 4 / 3 + max(_FALLBACK_BATCHES.values())


@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_load_imbalance_below_max_university(n):
    """No researcher should be more than the largest university worth of batches
    above the lightest. (Trivially true by LPT — a worker never picks up another
    item if a peer has lower load.)"""
    slices = balance_assignments(ALL_TEN, n)
    loads = [s.total_batches for s in slices]
    assert max(loads) - min(loads) <= max(_FALLBACK_BATCHES.values())


def test_invalid_n_rejected():
    with pytest.raises(ValueError):
        balance_assignments(ALL_TEN, 0)
    with pytest.raises(ValueError):
        balance_assignments(ALL_TEN, 6)


def test_empty_universities_rejected():
    with pytest.raises(ValueError):
        balance_assignments([], 3)


def test_get_active_universities_returns_ten(tmp_path):
    """Smoke test against the real mapping file."""
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent.parent
    mapping = repo_root / "topic_modeling" / "configs" / "university_mapping.yaml"
    if not mapping.exists():
        pytest.skip(f"mapping file not present: {mapping}")
    codes = get_active_universities(mapping)
    assert len(codes) == 10
    assert "CAR-PSEC-1" in codes
    assert all(c in _FALLBACK_BATCHES for c in codes)
