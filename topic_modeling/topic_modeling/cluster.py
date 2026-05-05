"""UMAP + HDBSCAN with grid search and NPMI/silhouette scoring.

Selection score = 0.5*NPMI + 0.3*silhouette + 0.2*(1 - outlier_rate).

NPMI is approximated via a co-occurrence count over the top c-TF-IDF terms per
cluster — a fast proxy that does not require a separate gensim CoherenceModel
pass on every grid point. The orchestrator may compute a more precise NPMI on
the WINNING configuration via topics.compute_npmi_full().
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from .logging_setup import setup_logger

log = setup_logger(__name__)


# --- UMAP ------------------------------------------------------------------

def run_umap(embeddings: np.ndarray, *, n_neighbors: int, n_components: int,
             metric: str, min_dist: float, random_state: int) -> np.ndarray:
    from umap import UMAP
    return UMAP(
        n_neighbors=n_neighbors,
        n_components=n_components,
        metric=metric,
        min_dist=min_dist,
        random_state=random_state,
    ).fit_transform(embeddings)


# --- HDBSCAN ---------------------------------------------------------------

def run_hdbscan(reduced: np.ndarray, *, min_cluster_size: int, min_samples: int,
                metric: str, cluster_selection_method: str):
    from hdbscan import HDBSCAN
    clusterer = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric=metric,
        cluster_selection_method=cluster_selection_method,
        prediction_data=True,
    )
    labels = clusterer.fit_predict(reduced)
    return clusterer, labels


# --- Scoring ---------------------------------------------------------------

def outlier_rate(labels: np.ndarray) -> float:
    return float((labels == -1).mean())


def silhouette_for_clusters(reduced: np.ndarray, labels: np.ndarray) -> float:
    """Silhouette over non-outlier points only. Returns 0.0 if not computable."""
    from sklearn.metrics import silhouette_score
    mask = labels != -1
    uniq = np.unique(labels[mask])
    if mask.sum() < 2 or len(uniq) < 2:
        return 0.0
    try:
        return float(silhouette_score(reduced[mask], labels[mask]))
    except Exception as e:
        log.warning("silhouette_score failed: %s", e)
        return 0.0


def fast_npmi(docs: list[str], labels: np.ndarray, *, top_n_per_cluster: int = 10,
              min_token_count: int = 5) -> float:
    """Approximate NPMI: average per-cluster pairwise NPMI over top-N tokens.

    A fast surrogate suitable for grid-search ranking. Tokenization is whitespace +
    lowercase; stopwords are NOT applied here (the orchestrator passes already-
    tokenizable text). For the WINNING config, prefer compute_npmi_full() in
    topics.py.
    """
    if (labels == -1).all():
        return 0.0

    # Per-doc token sets (binary, deduped per doc)
    tokenized = [set(t for t in _tokenize(d) if len(t) > 1) for d in docs]
    N = len(tokenized)

    # Global doc-frequency
    df: dict[str, int] = {}
    for toks in tokenized:
        for t in toks:
            df[t] = df.get(t, 0) + 1

    cluster_scores: list[float] = []
    for c in np.unique(labels):
        if c == -1:
            continue
        idx = np.where(labels == c)[0]
        if len(idx) < 2:
            continue
        # Top tokens by within-cluster doc frequency
        cf: dict[str, int] = {}
        for i in idx:
            for t in tokenized[i]:
                cf[t] = cf.get(t, 0) + 1
        candidates = [t for t, k in cf.items() if df.get(t, 0) >= min_token_count]
        candidates.sort(key=lambda t: cf[t], reverse=True)
        top = candidates[:top_n_per_cluster]
        if len(top) < 2:
            continue

        # Pairwise NPMI within the cluster
        scores: list[float] = []
        n_cluster = len(idx)
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                a, b = top[i], top[j]
                co = sum(1 for k in idx if a in tokenized[k] and b in tokenized[k])
                if co == 0:
                    scores.append(-1.0)
                    continue
                p_ab = co / n_cluster
                p_a = cf[a] / n_cluster
                p_b = cf[b] / n_cluster
                pmi = math.log(p_ab / (p_a * p_b))
                denom = -math.log(p_ab)
                if denom > 0:
                    scores.append(pmi / denom)
        if scores:
            cluster_scores.append(sum(scores) / len(scores))
    if not cluster_scores:
        return 0.0
    return float(sum(cluster_scores) / len(cluster_scores))


def _tokenize(s: str) -> list[str]:
    import re
    return re.findall(r"[a-z0-9]+", (s or "").lower())


# --- Composite score -------------------------------------------------------

def composite_score(*, npmi: float, silhouette: float, outlier_rate_val: float,
                    weights: dict[str, float]) -> float:
    return (weights["npmi"] * npmi
            + weights["silhouette"] * silhouette
            + weights["low_outlier_bonus"] * (1.0 - outlier_rate_val))


# --- Grid search -----------------------------------------------------------

def grid_search_hdbscan(
    embeddings: np.ndarray,
    docs: list[str],
    *,
    umap_cfg: dict,
    grid: dict,
    hdbscan_static: dict,
    weights: dict,
    min_cluster_count_floor: int = 0,
) -> tuple[dict, list[dict]]:
    """Returns (best_params_dict, all_results_list).

    best_params has keys: min_cluster_size, min_samples, npmi, silhouette,
    outlier_rate, score, plus the UMAP-reduced array stored as `_reduced`
    (numpy array, not JSON-serializable — strip before logging).

    If min_cluster_count_floor > 0, the selection prefers configs with
    n_clusters >= floor; only falls back to overall best score if NO config
    in the grid meets the floor. This prevents the score function from
    picking trivial 2-cluster solutions when more granularity is achievable.
    """
    reduced = run_umap(
        embeddings,
        n_neighbors=umap_cfg["n_neighbors"],
        n_components=umap_cfg["n_components"],
        metric=umap_cfg["metric"],
        min_dist=umap_cfg["min_dist"],
        random_state=umap_cfg["random_state"],
    )
    log.info("UMAP reduced %s -> %s", embeddings.shape, reduced.shape)

    results: list[dict] = []
    for mcs in grid["min_cluster_size"]:
        for ms in grid["min_samples"]:
            _, labels = run_hdbscan(
                reduced,
                min_cluster_size=mcs,
                min_samples=ms,
                metric=hdbscan_static["metric"],
                cluster_selection_method=hdbscan_static["cluster_selection_method"],
            )
            ot = outlier_rate(labels)
            sil = silhouette_for_clusters(reduced, labels)
            npmi = fast_npmi(docs, labels)
            score = composite_score(npmi=npmi, silhouette=sil,
                                    outlier_rate_val=ot, weights=weights)
            res = {
                "min_cluster_size": mcs,
                "min_samples": ms,
                "outlier_rate": round(ot, 4),
                "silhouette": round(sil, 4),
                "npmi": round(npmi, 4),
                "score": round(score, 4),
                "n_clusters": int(len(set(labels)) - (1 if -1 in labels else 0)),
            }
            log.info("grid mcs=%d ms=%d -> %s", mcs, ms, res)
            results.append(res)
    if not results:
        raise RuntimeError("Grid search produced no results (empty grid?)")

    # Hard constraint: prefer configs with n_clusters >= floor.
    # Falls back to overall best if NO config in the grid meets the floor.
    if min_cluster_count_floor > 0:
        eligible = [r for r in results if r["n_clusters"] >= min_cluster_count_floor]
        if eligible:
            best = max(eligible, key=lambda r: r["score"])
            log.info("Grid selection: chose mcs=%d ms=%d n_clusters=%d score=%.3f "
                     "from %d eligible configs (floor=%d)",
                     best["min_cluster_size"], best["min_samples"],
                     best["n_clusters"], best["score"],
                     len(eligible), min_cluster_count_floor)
        else:
            best = max(results, key=lambda r: r["score"])
            log.warning("Grid selection: NO config met n_clusters >= %d floor; "
                        "falling back to overall best (mcs=%d ms=%d n_clusters=%d)",
                        min_cluster_count_floor,
                        best["min_cluster_size"], best["min_samples"],
                        best["n_clusters"])
            best["_floor_fallback"] = True
    else:
        best = max(results, key=lambda r: r["score"])
    best["_reduced"] = reduced
    return best, results
