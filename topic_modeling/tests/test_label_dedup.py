"""Tests for intra-university label deduplication."""
from __future__ import annotations

from topic_modeling.labeling import dedupe_labels_intra_univ


def test_unique_labels_unchanged():
    labels = [
        {"topic_id": 0, "label": "Academic Stress", "flags": []},
        {"topic_id": 1, "label": "Cafeteria Food", "flags": []},
    ]
    keywords = {0: [("finals", 0.4)], 1: [("food", 0.3)]}
    out = dedupe_labels_intra_univ(labels, keywords)
    assert [r["label"] for r in out] == ["Academic Stress", "Cafeteria Food"]
    assert all("DISAMBIGUATED" not in r["flags"] for r in out)


def test_duplicate_labels_disambiguated():
    labels = [
        {"topic_id": 0, "label": "Academic Stress", "flags": []},
        {"topic_id": 1, "label": "Academic Stress", "flags": []},
    ]
    keywords = {
        0: [("finals", 0.5), ("review", 0.3)],
        1: [("enrollment", 0.4), ("queue", 0.2)],
    }
    out = dedupe_labels_intra_univ(labels, keywords)
    labels_out = sorted(r["label"] for r in out)
    assert labels_out == ["Academic Stress (enrollment)", "Academic Stress (finals)"]
    for r in out:
        assert "DISAMBIGUATED" in r["flags"]


def test_unlabeled_not_deduplicated():
    labels = [
        {"topic_id": 0, "label": "Unlabeled", "flags": ["API_GIVEUP"]},
        {"topic_id": 1, "label": "Unlabeled", "flags": ["API_GIVEUP"]},
    ]
    keywords = {0: [("a", 0.1)], 1: [("b", 0.1)]}
    out = dedupe_labels_intra_univ(labels, keywords)
    # Unlabeled stays unlabeled — dedup only applies to genuine labels
    assert all(r["label"] == "Unlabeled" for r in out)
    assert all("DISAMBIGUATED" not in r["flags"] for r in out)


def test_three_way_collision():
    labels = [
        {"topic_id": i, "label": "General Discussion", "flags": []} for i in range(3)
    ]
    keywords = {0: [("a", 0.4)], 1: [("b", 0.3)], 2: [("c", 0.2)]}
    out = dedupe_labels_intra_univ(labels, keywords)
    suffixes = sorted(r["label"] for r in out)
    assert suffixes == [
        "General Discussion (a)",
        "General Discussion (b)",
        "General Discussion (c)",
    ]
