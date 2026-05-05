"""Temporal-concentration scoring for event-driven topic detection.

Computes per-cluster temporal Gini coefficient on monthly bins. Clusters with
high concentration (Gini > 0.6) are flagged event-driven; the labeling stage
augments their prompt with the date range so the LLM produces event-specific
labels (e.g., "2026 Transportation Strike Response" instead of "Student Life
Concerns").

Why Gini?
- Gini = 0  : posts spread uniformly across all months → chronic / ongoing topic
- Gini ≈ 0.5: posts moderately concentrated in a few months
- Gini ≈ 1  : posts entirely in one month → discrete event

Threshold of 0.6 chosen empirically: a topic uniformly active for 4 of 12
months sits around 0.55 Gini; a topic concentrated in 1-2 months exceeds 0.7.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Iterable

EVENT_GINI_THRESHOLD = 0.6


def month_key(ts_unix: int | None) -> str | None:
    if ts_unix is None:
        return None
    return datetime.fromtimestamp(int(ts_unix), tz=timezone.utc).strftime("%Y-%m")


def gini(counts: Iterable[int]) -> float:
    """Gini coefficient over a list of bin counts. Returns 0.0 for empty/uniform."""
    counts = sorted(c for c in counts if c >= 0)
    n = len(counts)
    if n == 0:
        return 0.0
    total = sum(counts)
    if total == 0:
        return 0.0
    cum = 0.0
    for i, c in enumerate(counts, start=1):
        cum += i * c
    return float((2.0 * cum) / (n * total) - (n + 1.0) / n)


def _normalize_to_corpus_months(cluster_months: Counter, all_months: list[str]) -> list[int]:
    """Pad zero counts for months that exist in the corpus but not in the cluster.
    Without this, a cluster confined to 1 of 12 corpus months would still look
    'spread' if we only counted its own months."""
    return [cluster_months.get(m, 0) for m in all_months]


def cluster_temporal_signature(
    timestamps_unix: list[int | None],
    corpus_all_months: list[str],
) -> dict:
    """Per-cluster temporal stats:
        {
          "n_with_timestamp": int,
          "monthly_distribution": {"YYYY-MM": int, ...},
          "concentrated_months": ["YYYY-MM", ...],  # top months totaling ≥ 70%
          "gini": float,
          "is_event_driven": bool,
        }
    """
    months = [m for m in (month_key(ts) for ts in timestamps_unix) if m is not None]
    n_with_ts = len(months)
    if n_with_ts == 0:
        return {
            "n_with_timestamp": 0,
            "monthly_distribution": {},
            "concentrated_months": [],
            "gini": 0.0,
            "is_event_driven": False,
        }
    cluster_counts = Counter(months)
    padded = _normalize_to_corpus_months(cluster_counts, corpus_all_months)
    g = gini(padded)

    # "Concentrated months" = smallest set of months whose cumulative share ≥ 70%
    sorted_months = sorted(cluster_counts.items(), key=lambda kv: -kv[1])
    threshold = 0.70 * n_with_ts
    accum = 0
    concentrated: list[str] = []
    for month, c in sorted_months:
        concentrated.append(month)
        accum += c
        if accum >= threshold:
            break

    return {
        "n_with_timestamp": n_with_ts,
        "monthly_distribution": dict(cluster_counts),
        "concentrated_months": sorted(concentrated),
        "gini": round(g, 4),
        "is_event_driven": g >= EVENT_GINI_THRESHOLD,
    }


def corpus_month_keys(timestamps_unix: list[int | None]) -> list[str]:
    """Return the sorted list of YYYY-MM bins present in the whole corpus."""
    return sorted({month_key(ts) for ts in timestamps_unix if ts is not None} - {None})


def format_date_range(months: list[str]) -> str:
    """Pretty-print a list of YYYY-MM strings as a date range hint for the LLM."""
    if not months:
        return ""
    sorted_m = sorted(months)
    if len(sorted_m) == 1:
        return _human_month(sorted_m[0])
    return f"{_human_month(sorted_m[0])} — {_human_month(sorted_m[-1])}"


def _human_month(yyyy_mm: str) -> str:
    try:
        return datetime.strptime(yyyy_mm, "%Y-%m").strftime("%B %Y")
    except ValueError:
        return yyyy_mm
