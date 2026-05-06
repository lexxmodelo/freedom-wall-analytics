"""Validator tests: range clamp, reconciliation, sarcasm consistency."""
from __future__ import annotations

from vad_scoring.validator import clamp_and_check, reconcile_batch


# -------- clamp_and_check --------

def test_in_range_no_flags():
    rec = {"id": "a", "V": 3, "A": 5, "D": 7, "sarcasm": False}
    out = clamp_and_check(dict(rec))
    assert out["flags"] == []
    assert out["V"] == 3 and out["A"] == 5 and out["D"] == 7


def test_above_range_clamps_high():
    rec = {"id": "a", "V": 12, "A": 5, "D": 7, "sarcasm": False}
    out = clamp_and_check(dict(rec))
    assert out["V"] == 9
    assert "range_clamped" in out["flags"]
    assert "v_clamped" in out["flags"]


def test_below_range_clamps_low():
    rec = {"id": "a", "V": 0, "A": -3, "D": 7, "sarcasm": False}
    out = clamp_and_check(dict(rec))
    assert out["V"] == 1 and out["A"] == 1
    assert "v_clamped" in out["flags"] and "a_clamped" in out["flags"]


def test_float_score_rounded_and_flagged():
    rec = {"id": "a", "V": 3.7, "A": 5, "D": 7, "sarcasm": False}
    out = clamp_and_check(dict(rec))
    assert out["V"] == 4
    assert "non_integer_score" in out["flags"]


def test_sarcasm_high_valence_flag():
    rec = {"id": "a", "V": 8, "A": 5, "D": 5, "sarcasm": True}
    out = clamp_and_check(dict(rec))
    assert "sarcasm_high_valence" in out["flags"]


def test_sarcasm_low_valence_no_consistency_flag():
    rec = {"id": "a", "V": 2, "A": 5, "D": 5, "sarcasm": True}
    out = clamp_and_check(dict(rec))
    assert "sarcasm_high_valence" not in out["flags"]


# -------- reconcile_batch --------

def _expected_batch(ids):
    return [{"post_id": i, "univ_code": "X", "topic_id": 0, "topic_label": "t", "text": ""} for i in ids]


def test_reconcile_perfect_match():
    parsed = [
        {"id": "a", "V": 1, "A": 1, "D": 1, "sarcasm": False},
        {"id": "b", "V": 1, "A": 1, "D": 1, "sarcasm": False},
    ]
    result = reconcile_batch(parsed, _expected_batch(["a", "b"]))
    assert set(result.reconciled) == {"a", "b"}
    assert result.missing_ids == []
    assert result.extra_ids == []
    assert result.duplicate_ids == []


def test_reconcile_missing_id():
    parsed = [{"id": "a", "V": 1, "A": 1, "D": 1, "sarcasm": False}]
    result = reconcile_batch(parsed, _expected_batch(["a", "b", "c"]))
    assert set(result.reconciled) == {"a"}
    assert sorted(result.missing_ids) == ["b", "c"]
    assert result.extra_ids == []


def test_reconcile_extra_id_ignored():
    parsed = [
        {"id": "a", "V": 1, "A": 1, "D": 1, "sarcasm": False},
        {"id": "ZZZ", "V": 1, "A": 1, "D": 1, "sarcasm": False},
    ]
    result = reconcile_batch(parsed, _expected_batch(["a"]))
    assert set(result.reconciled) == {"a"}
    assert result.extra_ids == ["ZZZ"]


def test_reconcile_duplicate_takes_last():
    parsed = [
        {"id": "a", "V": 1, "A": 1, "D": 1, "sarcasm": False},
        {"id": "a", "V": 9, "A": 9, "D": 9, "sarcasm": True},
    ]
    result = reconcile_batch(parsed, _expected_batch(["a"]))
    assert "a" in result.duplicate_ids
    assert result.reconciled["a"]["V"] == 9
