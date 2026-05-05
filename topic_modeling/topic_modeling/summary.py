"""Cross-university summary generator.

After all universities in a researcher's batch complete, this writes
`validation/cross_university_summary.md` — a single committee-facing comparison
table that contextualizes the per-university topic counts.

Design intent (per chat 2026-05-06): cross-university topic-count variation
is a thesis FINDING, not a bug. The summary surfaces it transparently with
metrics that ARE comparable across universities (outlier rate, NPMI, silhouette,
temporal Gini), so reviewers can read variation as substance rather than as
methodological inconsistency.
"""
from __future__ import annotations

import collections
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io_utils import load_json


def _safe_load(path: Path) -> Any:
    try:
        return load_json(path) if path.exists() else None
    except Exception:
        return None


def _corpus_stats(input_dir: Path, fname: str) -> dict:
    """Read the cleaned posts file once to extract n_posts, language mix,
    and date range. Used as context for each university in the summary."""
    f = input_dir / fname
    if not f.exists():
        return {}
    try:
        with f.open("r", encoding="utf-8") as fp:
            posts = json.load(fp)
    except Exception:
        return {}

    n_posts = len(posts)
    langs = collections.Counter(p.get("language_detected", "?") for p in posts)
    top3 = langs.most_common(3)
    top_lang_label = ", ".join(f"{l} {c*100//max(n_posts,1)}%" for l, c in top3)

    timestamps = [p.get("timestamp_unix") for p in posts if p.get("timestamp_unix")]
    if timestamps:
        dmin = datetime.fromtimestamp(min(timestamps), tz=timezone.utc).strftime("%Y-%m")
        dmax = datetime.fromtimestamp(max(timestamps), tz=timezone.utc).strftime("%Y-%m")
        date_range = f"{dmin} → {dmax}"
    else:
        date_range = "—"

    return {
        "n_posts": n_posts,
        "top_languages": top_lang_label,
        "date_range": date_range,
    }


def _label_quality_signals(labels: list[dict]) -> dict:
    """Lazy-label percentage, event-driven percentage, API failure count."""
    if not labels:
        return {"n_labels": 0, "lazy_pct": 0.0, "event_pct": 0.0, "api_fails": 0}
    n = len(labels)
    lazy = sum(1 for r in labels if "LAZY_LABEL" in r.get("flags", []))
    event = sum(1 for r in labels if "EVENT_DRIVEN" in r.get("flags", []))
    fails = sum(1 for r in labels if "API_GIVEUP" in r.get("flags", [])
                or "MALFORMED_OUTPUT" in r.get("flags", []))
    return {
        "n_labels": n,
        "lazy_pct": round(lazy / n, 3),
        "event_pct": round(event / n, 3),
        "api_fails": fails,
    }


def write_cross_university_summary(
    *,
    root: Path,
    outputs_dir: Path,
    mapping: dict,
    input_dir: Path,
    summary_path: Path,
) -> dict:
    """Walk every univ_code in mapping with an active=true entry, gather
    per-university metrics, and write the summary markdown file.

    Returns a dict of per-univ stats for programmatic consumers.
    """
    rows: list[dict] = []
    for fname, m in (mapping.get("mappings") or {}).items():
        if not m.get("active"):
            continue
        code = m.get("code")
        if not code or str(code).upper() == "TBD":
            continue

        univ_dir = outputs_dir / code
        meta = _safe_load(univ_dir / "topic_metadata.json")
        labels = _safe_load(univ_dir / "topic_labels.json") or []
        dtm = _safe_load(univ_dir / "topics_over_time.json") or {}
        corpus = _corpus_stats(input_dir, fname)

        label_q = _label_quality_signals(labels)
        rows.append({
            "fname": fname,
            "code": code,
            "alias": m.get("school_alias", ""),
            "region": m.get("region", ""),
            "n_posts": corpus.get("n_posts", 0),
            "top_languages": corpus.get("top_languages", ""),
            "date_range": corpus.get("date_range", "—"),
            "completed": meta is not None,
            "n_topics": (meta or {}).get("n_topics", 0),
            "outlier_rate": (meta or {}).get("outlier_rate", None),
            "npmi": (meta or {}).get("npmi", None),
            "silhouette": (meta or {}).get("silhouette", None),
            "n_labels": label_q["n_labels"],
            "lazy_pct": label_q["lazy_pct"],
            "event_pct": label_q["event_pct"],
            "api_fails": label_q["api_fails"],
            "dtm_bins": dtm.get("n_bins", 0),
            "dtm_skipped": dtm.get("skipped", False),
        })

    completed = [r for r in rows if r["completed"]]
    pending = [r for r in rows if not r["completed"]]

    md = _render_markdown(rows, completed, pending)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(md, encoding="utf-8")
    return {"rows": rows, "n_completed": len(completed), "n_pending": len(pending)}


def _render_markdown(rows: list[dict], completed: list[dict], pending: list[dict]) -> str:
    out: list[str] = []
    out.append("# Cross-University Topic Modeling Summary")
    out.append("")
    out.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    out.append("")
    out.append(f"Universities completed: **{len(completed)}** of {len(rows)}")
    out.append("")

    if completed:
        out.append("## Completed universities")
        out.append("")
        out.append("| Code | Alias | Region | Posts | Top languages | Date range | Topics | Outlier % | NPMI | Silhouette | Lazy labels % | Event-driven % | API fails |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in sorted(completed, key=lambda r: r["code"]):
            out.append(
                f"| `{r['code']}` | {r['alias']} | {r['region']} | "
                f"{r['n_posts']:,} | {r['top_languages']} | {r['date_range']} | "
                f"**{r['n_topics']}** | "
                f"{r['outlier_rate']*100:.1f}% | "
                f"{r['npmi']:.3f} | "
                f"{r['silhouette']:.3f} | "
                f"{r['lazy_pct']*100:.0f}% | "
                f"{r['event_pct']*100:.0f}% | "
                f"{r['api_fails']} |"
            )
        out.append("")

        # Pivot stats
        topic_counts = [r["n_topics"] for r in completed]
        outlier_rates = [r["outlier_rate"] for r in completed if r["outlier_rate"] is not None]
        npmis = [r["npmi"] for r in completed if r["npmi"] is not None]
        out.append("## Aggregate statistics")
        out.append("")
        out.append("| Metric | Min | Median | Max |")
        out.append("|---|---|---|---|")
        out.append(f"| Topics per university | {min(topic_counts)} | "
                   f"{sorted(topic_counts)[len(topic_counts)//2]} | {max(topic_counts)} |")
        if outlier_rates:
            out.append(f"| Outlier rate | {min(outlier_rates)*100:.1f}% | "
                       f"{sorted(outlier_rates)[len(outlier_rates)//2]*100:.1f}% | "
                       f"{max(outlier_rates)*100:.1f}% |")
        if npmis:
            out.append(f"| NPMI | {min(npmis):.3f} | "
                       f"{sorted(npmis)[len(npmis)//2]:.3f} | {max(npmis):.3f} |")
        out.append("")

    if pending:
        out.append("## Universities not yet complete")
        out.append("")
        for r in sorted(pending, key=lambda r: r["code"]):
            out.append(f"- `{r['code']}` ({r['alias']}) — {r['n_posts']:,} posts in {r['fname']}")
        out.append("")

    out.append("## How to read topic-count variation")
    out.append("")
    out.append(
        "Cross-university topic-count differences are a **finding**, not a "
        "methodological flaw. Each university's Freedom Wall has its own "
        "linguistic mix, time window, and posting culture, which produce "
        "genuinely different density structures in the embedding space. "
        "The pipeline's `target_topic_count` is a *ceiling* (via reduce_topics) "
        "rather than a target — universities with naturally clean structure "
        "(few well-separated themes) keep their natural count; universities "
        "with over-fragmented structure get merged down to the target.")
    out.append("")
    out.append(
        "For fair cross-university comparison prefer **outlier_rate** "
        "(discourse cohesion), **NPMI** (within-topic coherence), and "
        "**event_driven %** (temporal concentration). Raw topic count alone "
        "should be interpreted alongside these metrics in the thesis discussion.")
    out.append("")
    return "\n".join(out)
