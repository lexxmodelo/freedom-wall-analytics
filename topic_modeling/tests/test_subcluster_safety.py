"""Regression tests for the dump-cluster annihilation bug fixed 2026-05-06.

If sub-clustering inside a dump cluster fails to find any real sub-clusters,
merge_subclusters_back must NOT erase the parent cluster by mapping every
member to -1. Doing so caused MM-PUB-1 to drop from 3 topics to 1 with 97.48%
outliers (action_log.md ACTION-018, 019, 020, 021).
"""
from __future__ import annotations

import numpy as np

from topic_modeling.subcluster import merge_subclusters_back


def test_all_minus_one_preserves_parent_cluster():
    """When sub-clustering produces only -1 labels (no density found),
    the parent cluster must remain intact."""
    primary = np.array([0, 0, 0, 1, 1, 1, 1, 2, 2])
    sub = np.array([-1, -1, -1, -1])  # all 4 members of cluster 1 → noise

    new, info = merge_subclusters_back(primary, dump_cluster_id=1,
                                       sub_labels=sub, next_topic_id=3)

    # Parent cluster 1 should still exist with its 4 members
    assert (new == 1).sum() == 4
    assert (new == -1).sum() == 0   # NOT annihilated
    assert list(new) == list(primary)
    assert info["skipped"] is True
    assert info["n_subclusters"] == 0
    assert info["new_topic_ids"] == []


def test_single_subcluster_preserves_parent():
    """If HDBSCAN puts every member in one sub-cluster (no -1, no split),
    no real split happened — keep the parent intact."""
    primary = np.array([0, 0, 0, 1, 1, 1, 1, 2, 2])
    sub = np.array([0, 0, 0, 0])

    new, info = merge_subclusters_back(primary, dump_cluster_id=1,
                                       sub_labels=sub, next_topic_id=3)

    assert list(new) == list(primary)
    assert info["skipped"] is True


def test_real_split_gets_applied():
    """When sub-clustering finds genuine sub-clusters, the split happens
    and new topic IDs are assigned starting at next_topic_id."""
    primary = np.array([0, 0, 0, 1, 1, 1, 1, 1, 1, 2, 2])
    # cluster 1 has 6 members; sub-cluster splits into two real groups
    sub = np.array([0, 0, 0, 1, 1, 1])

    new, info = merge_subclusters_back(primary, dump_cluster_id=1,
                                       sub_labels=sub, next_topic_id=3)

    # First 3 members of cluster 1 keep parent id (1); last 3 get new id (3)
    assert list(new) == [0, 0, 0, 1, 1, 1, 3, 3, 3, 2, 2]
    assert info["skipped"] is False
    assert info["n_subclusters"] == 2
    assert info["new_topic_ids"] == [3]


def test_split_with_some_outliers():
    """Mixed case: real sub-clusters AND some -1 outliers from sub-clustering.
    Per ACTION-055 fix: sub-pass -1 keeps parent cluster id (NOT global -1) —
    those docs are still in their original parent's theme; the sub-pass just
    couldn't find finer structure for them."""
    primary = np.array([0, 0, 1, 1, 1, 1, 1, 2, 2])
    # cluster 1 has 5 members: 2 → sub 0, 2 → sub 1, 1 → sub-noise
    sub = np.array([0, 0, 1, 1, -1])

    new, info = merge_subclusters_back(primary, dump_cluster_id=1,
                                       sub_labels=sub, next_topic_id=3)

    # Cluster 1 members map: [0,0]→1 (parent), [1,1]→3 (new sub), [-1]→1 (parent)
    assert list(new) == [0, 0, 1, 1, 3, 3, 1, 2, 2]
    assert info["skipped"] is False
    assert info["n_subclusters"] == 2
    assert info["n_outliers_in_sub_kept_in_parent"] == 1


def test_no_dump_cluster_id_in_primary_does_not_crash():
    """Defensive: if dump_cluster_id has no members in primary, function
    handles the empty case (member_indices is empty, sub_labels must be too)."""
    primary = np.array([0, 0, 2, 2, 2])
    sub = np.array([])  # zero members

    new, info = merge_subclusters_back(primary, dump_cluster_id=99,
                                       sub_labels=sub, next_topic_id=3)
    assert list(new) == list(primary)
