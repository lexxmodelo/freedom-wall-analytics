"""BERTopic wrapper, c-TF-IDF extraction, and soft-cluster reassignment.

The orchestrator owns the post-list and embeddings; this module wraps BERTopic
so the rest of the pipeline doesn't need to know about its internals.

Soft reassignment: outlier docs (topic_id == -1) whose max-probability across
known topics meets or exceeds the threshold are reassigned to the argmax topic.
This implements methodology_changes.md §3.1 (line 217).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .logging_setup import setup_logger
from .textprep import strip_placeholders_batch

log = setup_logger(__name__)


def build_bertopic(
    docs: list[str],
    embeddings: np.ndarray,
    *,
    umap_cfg: dict,
    hdbscan_params: dict,
    stopwords: list[str],
    ngram_range: tuple[int, int] = (1, 2),
):
    """Construct + fit a BERTopic model with representation_model=None and
    custom UMAP/HDBSCAN/Vectorizer components.

    Anonymization placeholders ([REDACTED_NAME], [CAR], etc.) are stripped from
    docs before they reach c-TF-IDF; otherwise these tokens dominate the top
    keywords across every cluster (in SLU they appeared in 79% of posts).
    Embeddings are NOT regenerated here — the caller is responsible for having
    embedded already-cleaned text.
    """
    from bertopic import BERTopic
    from umap import UMAP
    from hdbscan import HDBSCAN
    from sklearn.feature_extraction.text import CountVectorizer

    cleaned_docs = strip_placeholders_batch(docs)

    umap_model = UMAP(
        n_neighbors=umap_cfg["n_neighbors"],
        n_components=umap_cfg["n_components"],
        metric=umap_cfg["metric"],
        min_dist=umap_cfg["min_dist"],
        random_state=umap_cfg["random_state"],
    )
    hdbscan_model = HDBSCAN(
        min_cluster_size=hdbscan_params["min_cluster_size"],
        min_samples=hdbscan_params["min_samples"],
        metric=hdbscan_params.get("metric", "euclidean"),
        cluster_selection_method=hdbscan_params.get("cluster_selection_method", "eom"),
        prediction_data=True,
    )
    vectorizer = CountVectorizer(
        stop_words=list(stopwords) if stopwords else None,
        ngram_range=ngram_range,
    )
    topic_model = BERTopic(
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        vectorizer_model=vectorizer,
        representation_model=None,           # decoupled labeling per methodology
        calculate_probabilities=True,        # needed for soft reassignment
        verbose=True,
    )
    # Pass cleaned_docs so c-TF-IDF runs on placeholder-free text.
    # Embeddings were already produced by the caller from the same cleaned text.
    topics, probs = topic_model.fit_transform(cleaned_docs, embeddings=embeddings)
    return topic_model, np.asarray(topics), probs


def soft_reassign_outliers(topics: np.ndarray, probs: np.ndarray | None,
                           *, threshold: float) -> tuple[np.ndarray, dict]:
    """Reassign topic_id==-1 docs to argmax topic when their max prob >= threshold.

    Returns (new_topics, stats_dict).
    """
    if probs is None:
        log.warning("No probability matrix; skipping soft reassignment")
        return topics.copy(), {"reassigned": 0, "skipped": True}

    new = topics.copy()
    outlier_idx = np.where(topics == -1)[0]
    n_reassigned = 0
    if len(outlier_idx) == 0 or probs.size == 0:
        return new, {"reassigned": 0, "outlier_count": int(len(outlier_idx))}

    # probs may be (N, K) or 1-d depending on BERTopic version
    if probs.ndim == 1:
        # Cannot soft-reassign without per-topic probs — skip
        return new, {"reassigned": 0, "skipped": "1d_probs"}

    for i in outlier_idx:
        row = probs[i]
        if row.size == 0:
            continue
        argmax = int(np.argmax(row))
        if float(row[argmax]) >= threshold:
            new[i] = argmax
            n_reassigned += 1

    log.info(
        "Soft reassignment: %d/%d outliers reassigned at threshold=%.2f",
        n_reassigned, len(outlier_idx), threshold,
    )
    return new, {
        "reassigned": int(n_reassigned),
        "outlier_count": int(len(outlier_idx)),
        "threshold": threshold,
        "post_reassignment_outlier_rate": float((new == -1).mean()),
    }


def extract_keywords(topic_model, top_n: int = 10) -> dict[int, list[tuple[str, float]]]:
    """Return {topic_id: [(word, c-tf-idf score), ...]} for non-outlier topics."""
    out: dict[int, list[tuple[str, float]]] = {}
    raw = topic_model.get_topics()
    for tid, terms in raw.items():
        if tid == -1:
            continue
        out[int(tid)] = [(w, float(s)) for w, s in terms[:top_n]]
    return out


def extract_representative_docs(topic_model, docs: list[str], post_ids: list[str],
                                top_n: int = 5) -> dict[int, list[dict]]:
    """Return {topic_id: [{"post_id": ..., "text": ...}, ...]} for non-outlier topics.

    BERTopic's get_representative_docs() returns texts; we also need post_ids,
    so we look each text back up by exact match within the topic's doc set.
    """
    rep_texts = topic_model.get_representative_docs()
    text_to_id: dict[str, str] = {}
    for pid, txt in zip(post_ids, docs):
        text_to_id.setdefault(txt, pid)
    out: dict[int, list[dict]] = {}
    for tid, texts in rep_texts.items():
        if tid == -1:
            continue
        out[int(tid)] = [
            {"post_id": text_to_id.get(t, "<unknown>"),
             "text": (t[:280] + "…") if len(t) > 280 else t}
            for t in texts[:top_n]
        ]
    return out


def serialize_assignments(post_ids: list[str], topics: np.ndarray,
                          probs: np.ndarray | None,
                          reassigned_indices: set[int] | None = None) -> list[dict]:
    """post_id -> topic_id mapping with probability + soft_reassigned flag."""
    out: list[dict] = []
    for i, pid in enumerate(post_ids):
        rec = {"post_id": pid, "topic_id": int(topics[i])}
        if probs is not None and probs.ndim == 2 and probs.shape[1] > 0:
            tid = int(topics[i])
            if 0 <= tid < probs.shape[1]:
                rec["probability"] = round(float(probs[i, tid]), 4)
        if reassigned_indices and i in reassigned_indices:
            rec["soft_reassigned"] = True
        out.append(rec)
    return out


def topic_metadata(topics: np.ndarray, npmi: float, silhouette: float,
                   outlier_rate: float, hdbscan_params: dict) -> dict:
    """Per-university model metadata (not per-topic)."""
    unique, counts = np.unique(topics, return_counts=True)
    sizes = {int(t): int(c) for t, c in zip(unique, counts)}
    return {
        "n_topics": int(len(unique) - (1 if -1 in unique else 0)),
        "n_outliers": int(sizes.get(-1, 0)),
        "outlier_rate": round(outlier_rate, 4),
        "npmi": round(npmi, 4),
        "silhouette": round(silhouette, 4),
        "topic_sizes": sizes,
        "hdbscan_params": hdbscan_params,
    }


def save_model(topic_model, path: Path) -> None:
    """Persist the BERTopic model. Uses BERTopic's native pickle save."""
    path.parent.mkdir(parents=True, exist_ok=True)
    topic_model.save(str(path), serialization="pickle")
