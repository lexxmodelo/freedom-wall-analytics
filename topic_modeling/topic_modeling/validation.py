"""Per-university and per-researcher validation reporting.

Computes the QA checklist from plan §5 and writes:
- validation/outlier_report.json
- validation/lazy_label_flags.json
- validation/label_consistency_check.json (intra-researcher; merge.py does cross)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .io_utils import load_json, write_json
from .logging_setup import setup_logger

log = setup_logger(__name__)


def assess_university(
    *,
    univ_code: str,
    n_posts: int,
    metadata: dict,
    labels: list[dict],
    cache_dir: Path,
    cfg: dict,
) -> dict:
    """Run all QA checks for one university; return a structured assessment."""
    checks: dict[str, Any] = {}

    outlier = float(metadata.get("outlier_rate", 1.0))
    checks["outlier_rate_ok"] = outlier <= cfg["outlier_rate_warning_threshold"]

    sizes = {int(t): int(c) for t, c in metadata.get("topic_sizes", {}).items()}
    sizes.pop(-1, None)
    n_topics_with_min = sum(1 for s in sizes.values() if s >= 10)
    checks["min_topics_ok"] = n_topics_with_min >= cfg["min_topics_required"]
    checks["n_topics_with_ge10_posts"] = n_topics_with_min

    n_lazy = sum(1 for r in labels if "LAZY_LABEL" in r.get("flags", []))
    n_labels = max(len(labels), 1)
    checks["lazy_label_pct"] = round(n_lazy / n_labels, 4)
    checks["lazy_label_ok"] = (n_lazy / n_labels) <= cfg["lazy_label_max_pct"]

    checks["npmi_ok"] = float(metadata.get("npmi", 0.0)) >= cfg["min_npmi_required"]

    cache_files = list((cache_dir / univ_code).glob("*.json")) if (cache_dir / univ_code).exists() else []
    checks["cache_count_matches"] = len(cache_files) == len(labels)

    versions = set()
    for r in labels:
        v = (r.get("response_meta") or {}).get("headers", {}).get("x-model-version")
        if v:
            versions.add(v)
    checks["model_version_drift"] = len(versions) > 1
    checks["model_versions_seen"] = sorted(versions)

    needs_review = not all([
        checks["outlier_rate_ok"],
        checks["min_topics_ok"],
        checks["lazy_label_ok"],
        checks["npmi_ok"],
        checks["cache_count_matches"],
    ])

    return {
        "univ_code": univ_code,
        "n_posts": n_posts,
        "outlier_rate": round(outlier, 4),
        "n_topics": int(metadata.get("n_topics", 0)),
        "checks": checks,
        "needs_review": needs_review,
    }


def write_outlier_report(path: Path, assessments: list[dict]) -> None:
    high = [a for a in assessments
            if a["outlier_rate"] > 0.60]   # threshold from plan §5
    write_json(path, {
        "n_universities": len(assessments),
        "n_high_outlier": len(high),
        "high_outlier_unis": [a["univ_code"] for a in high],
        "details": assessments,
    })


def write_lazy_label_flags(path: Path, all_labels_by_univ: dict[str, list[dict]]) -> None:
    out: dict[str, list[dict]] = {}
    for univ, labels in all_labels_by_univ.items():
        flagged = [
            {"topic_id": r["topic_id"], "label": r["label"], "flags": r.get("flags", [])}
            for r in labels if "LAZY_LABEL" in r.get("flags", [])
        ]
        if flagged:
            out[univ] = flagged
    write_json(path, out)


def intra_researcher_label_check(path: Path,
                                 all_labels_by_univ: dict[str, list[dict]]) -> None:
    """Surface duplicate labels across the universities one researcher trained.

    Cross-researcher harmonization is a separate merge step (merge.py).
    """
    seen: dict[str, list[dict]] = {}
    for univ, labels in all_labels_by_univ.items():
        for r in labels:
            lbl = r["label"]
            if lbl == "Unlabeled":
                continue
            seen.setdefault(lbl, []).append({"univ": univ, "topic_id": r["topic_id"]})
    duplicates = {lbl: occ for lbl, occ in seen.items() if len(occ) > 1}
    write_json(path, {
        "n_duplicate_labels": len(duplicates),
        "duplicates": duplicates,
    })


def assignments_invariant_check(univ_code: str, post_ids: list[str],
                                assignments_path: Path,
                                labels_path: Path) -> dict:
    """Verify: every input post_id appears exactly once in assignments,
    and every non-outlier topic has a corresponding label."""
    assignments = load_json(assignments_path)
    labels = load_json(labels_path)
    assigned_ids = [a["post_id"] for a in assignments]
    counts: dict[str, int] = {}
    for pid in assigned_ids:
        counts[pid] = counts.get(pid, 0) + 1
    missing = [pid for pid in post_ids if pid not in counts]
    extra = [pid for pid in counts if pid not in set(post_ids)]
    duplicated = [pid for pid, c in counts.items() if c > 1]

    label_topic_ids = {r["topic_id"] for r in labels}
    assigned_topic_ids = {a["topic_id"] for a in assignments if a["topic_id"] != -1}
    unlabeled = sorted(assigned_topic_ids - label_topic_ids)
    return {
        "univ_code": univ_code,
        "n_posts_input": len(post_ids),
        "n_posts_assigned": len(assigned_ids),
        "missing_post_ids": missing[:10],
        "extra_post_ids": extra[:10],
        "duplicated_post_ids": duplicated[:10],
        "topics_assigned_without_label": unlabeled,
        "ok": (not missing) and (not extra) and (not duplicated) and (not unlabeled),
    }
