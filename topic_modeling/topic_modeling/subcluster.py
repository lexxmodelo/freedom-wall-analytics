"""Two-stage sub-clustering — split clusters that swallow >20% of the corpus.

When the primary pass dumps a large fraction of posts into one cluster (a
common KMeans failure mode and an occasional HDBSCAN outcome on noisy
corpora), this module re-clusters JUST that cluster's documents with stricter
parameters. The new sub-clusters get fresh topic IDs that don't collide with
existing ones.

Used by both:
- the production BERTopic flow (pipeline.py): re-clusters the dump cluster's
  member docs with the outlier_recovery hyperparameter grid
- the SLU KMeans demo: same idea, but with a smaller k inside

This is a defensive measure. The first-pass clustering should ideally not
need this — but when it does, surfacing the buried granular topics matters
more than algorithmic purity.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

DUMP_CLUSTER_THRESHOLD = 0.20  # cluster holding > 20% of corpus → split


def find_dump_clusters(labels: np.ndarray, *, threshold: float = DUMP_CLUSTER_THRESHOLD) -> list[int]:
    """Return cluster IDs (excluding -1 outliers) that hold > threshold of the corpus."""
    n = len(labels)
    if n == 0:
        return []
    out: list[int] = []
    for cid in np.unique(labels):
        if cid == -1:
            continue
        share = float((labels == cid).sum()) / n
        if share > threshold:
            out.append(int(cid))
    return out


def subcluster_kmeans(
    member_X: np.ndarray,
    *,
    k: int = 8,
    seed: int = 42,
) -> np.ndarray:
    """Re-cluster the SVD-reduced rows of one dump cluster with KMeans.

    Used by the SLU demo. The production pipeline uses subcluster_hdbscan instead.
    Returns local labels (0 .. k-1) of length len(member_X).
    """
    from sklearn.cluster import KMeans
    if len(member_X) < k * 2:
        return np.zeros(len(member_X), dtype=int)
    km = KMeans(n_clusters=k, random_state=seed, n_init=5, max_iter=200, init="k-means++")
    return km.fit_predict(member_X)


def subcluster_hdbscan(
    member_reduced: np.ndarray,
    *,
    min_cluster_size: int = 20,
    min_samples: int = 5,
) -> np.ndarray:
    """Production sub-clustering: HDBSCAN on the dump cluster's UMAP-reduced rows.

    Returns local labels (-1 outlier or 0+) of length len(member_reduced).
    """
    from hdbscan import HDBSCAN
    if len(member_reduced) < min_cluster_size * 2:
        return np.zeros(len(member_reduced), dtype=int)
    return HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        cluster_selection_method="eom",
        prediction_data=False,
    ).fit_predict(member_reduced)


def merge_subclusters_back(
    primary_labels: np.ndarray,
    dump_cluster_id: int,
    sub_labels: np.ndarray,
    *,
    next_topic_id: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Merge sub-cluster labels back into the primary label array.

    The original dump cluster ID stays for sub_labels==0 (the "main" sub-cluster
    that inherits the parent identity). All other sub-cluster IDs get fresh
    topic IDs starting at next_topic_id.

    Returns (new_labels, mapping_dict) where mapping_dict records what got split.
    """
    new_labels = primary_labels.copy()
    member_mask = primary_labels == dump_cluster_id
    member_indices = np.where(member_mask)[0]
    assert len(member_indices) == len(sub_labels), \
        f"member count {len(member_indices)} != sub_label count {len(sub_labels)}"

    sub_id_to_topic_id: dict[int, int] = {}
    next_id = next_topic_id
    for sub in sorted(set(sub_labels.tolist())):
        if sub == -1:
            sub_id_to_topic_id[sub] = -1   # outliers in sub-clustering go to noise
        elif sub == 0:
            sub_id_to_topic_id[sub] = dump_cluster_id   # largest sub keeps parent id
        else:
            sub_id_to_topic_id[sub] = next_id
            next_id += 1

    for local_idx, sub in enumerate(sub_labels):
        new_labels[member_indices[local_idx]] = sub_id_to_topic_id[sub]

    return new_labels, {
        "dump_cluster_id": dump_cluster_id,
        "n_members": int(len(member_indices)),
        "n_subclusters": int(sum(1 for v in sub_id_to_topic_id.values() if v != -1)),
        "n_outliers_in_sub": int(sum(1 for s in sub_labels if s == -1)),
        "new_topic_ids": [v for k, v in sub_id_to_topic_id.items() if k > 0],
    }
