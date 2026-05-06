"""Cross-researcher merge step (menu option 9, run by lead only).

Combines every results/researcher_*/<CODE>_vad_scores.jsonl file into:
  - merged_outputs/all_vad_scores.json       — single canonical list
  - merged_outputs/vad_statistics_per_topic.json

Refuses to run unless every researcher's checkpoint shows complete OR the
caller explicitly passes force=True (used by the menu only after warning the
user).
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Iterable

from .io_utils import load_json, load_jsonl, write_json
from .logging_setup import setup_logger

log = setup_logger(__name__)


def find_researcher_dirs(results_root: Path) -> list[Path]:
    if not results_root.exists():
        return []
    return sorted(p for p in results_root.iterdir() if p.is_dir() and p.name.startswith("researcher_"))


def find_checkpoint_dirs(checkpoints_root: Path) -> list[Path]:
    if not checkpoints_root.exists():
        return []
    return sorted(p for p in checkpoints_root.iterdir() if p.is_dir() and p.name.startswith("researcher_"))


def all_complete(checkpoint_root: Path) -> tuple[bool, list[str]]:
    """Returns (all_done, list_of_incomplete_descriptions)."""
    incomplete: list[str] = []
    for rdir in find_checkpoint_dirs(checkpoint_root):
        for state_file in rdir.glob("*_state.json"):
            try:
                data = load_json(state_file)
                if not data.get("complete"):
                    incomplete.append(
                        f"{rdir.name}/{state_file.stem}: "
                        f"{data.get('last_completed_batch', -1) + 1}/{data.get('total_batches', '?')} batches"
                    )
            except Exception as e:
                incomplete.append(f"{rdir.name}/{state_file.stem}: corrupted ({e})")
    return (len(incomplete) == 0, incomplete)


def collect_records(results_root: Path) -> Iterable[dict]:
    """Yield every VAD record across all researchers and universities."""
    for rdir in find_researcher_dirs(results_root):
        for jsonl_file in sorted(rdir.glob("*_vad_scores.jsonl")):
            for rec in load_jsonl(jsonl_file):
                yield rec


def merge(
    *,
    results_root: Path,
    checkpoint_root: Path,
    output_root: Path,
    force: bool = False,
) -> dict:
    """Run the merge. Returns a summary dict with counts and dedupe info."""
    done, incomplete = all_complete(checkpoint_root)
    if not done and not force:
        raise RuntimeError(
            "Cannot merge: not all researchers have completed. Incomplete:\n  - "
            + "\n  - ".join(incomplete)
        )

    output_root.mkdir(parents=True, exist_ok=True)

    # First pass: collect, dedupe by post_id (latest scored_at wins).
    by_id: dict[str, dict] = {}
    duplicate_count = 0
    total_seen = 0
    for rec in collect_records(results_root):
        total_seen += 1
        pid = rec.get("post_id")
        if not pid:
            continue
        if pid in by_id:
            duplicate_count += 1
            existing = by_id[pid]
            if rec.get("scored_at", "") > existing.get("scored_at", ""):
                by_id[pid] = rec
        else:
            by_id[pid] = rec

    records = sorted(by_id.values(), key=lambda r: (r.get("univ_code", ""), r.get("post_id", "")))
    write_json(output_root / "all_vad_scores.json", records)

    # Second pass: per-(univ_code, topic_label) statistics.
    stats: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "count": 0, "V": [], "A": [], "D": [], "sarcasm_count": 0,
        "flag_counts": defaultdict(int),
    })
    for r in records:
        key = (r["univ_code"], r.get("topic_label", "Unclassified"))
        s = stats[key]
        s["count"] += 1
        s["V"].append(r["V"])
        s["A"].append(r["A"])
        s["D"].append(r["D"])
        if r.get("sarcasm"):
            s["sarcasm_count"] += 1
        for f in r.get("flags") or []:
            s["flag_counts"][f] += 1

    out_stats: list[dict] = []
    for (code, label), s in sorted(stats.items()):
        out_stats.append({
            "univ_code": code,
            "topic_label": label,
            "n": s["count"],
            "V_mean": round(mean(s["V"]), 3) if s["V"] else None,
            "V_median": median(s["V"]) if s["V"] else None,
            "A_mean": round(mean(s["A"]), 3) if s["A"] else None,
            "A_median": median(s["A"]) if s["A"] else None,
            "D_mean": round(mean(s["D"]), 3) if s["D"] else None,
            "D_median": median(s["D"]) if s["D"] else None,
            "sarcasm_pct": round(100.0 * s["sarcasm_count"] / s["count"], 2) if s["count"] else 0.0,
            "flag_counts": dict(s["flag_counts"]),
        })
    write_json(output_root / "vad_statistics_per_topic.json", out_stats)

    summary = {
        "researchers_present": len(find_researcher_dirs(results_root)),
        "total_records_seen": total_seen,
        "unique_post_ids": len(by_id),
        "duplicates_resolved": duplicate_count,
        "topics_summarised": len(out_stats),
        "out_all_scores": str((output_root / "all_vad_scores.json").relative_to(output_root.parent)),
        "out_statistics": str((output_root / "vad_statistics_per_topic.json").relative_to(output_root.parent)),
        "incomplete_warnings": incomplete if force else [],
    }
    log.info("Merge complete: %s", summary)
    return summary
