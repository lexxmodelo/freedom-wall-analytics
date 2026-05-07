"""Build per-university dashboard JSONs from preprocessing + topic_modeling + vad_scoring.

Runs once per dashboard refresh. Outputs to dashboard/data/.

Usage:
    python dashboard/etl/build_dashboard_data.py
    python dashboard/etl/build_dashboard_data.py --univ CAR-PUB-1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PREPROC_DIR = ROOT / "preprocessing" / "output"
TOPIC_DIR = ROOT / "topic_modeling" / "outputs"
VAD_DIR = ROOT / "vad_scoring" / "results"
MAPPING_YAML = ROOT / "topic_modeling" / "configs" / "university_mapping.yaml"
OUT_DIR = ROOT / "dashboard" / "data"

TS_MIN_VALID = 1577836800   # 2020-01-01
TS_MAX_VALID = int(time.time()) + 365 * 24 * 3600


def load_mapping() -> dict[str, dict]:
    raw = yaml.safe_load(MAPPING_YAML.read_text(encoding="utf-8"))
    out = {}
    for filename, meta in raw.get("mappings", {}).items():
        if not meta.get("active", True):
            continue
        out[meta["code"]] = {
            "source_file": filename,
            "school_alias": meta.get("school_alias", ""),
            "region": meta.get("region", ""),
            "confidence": meta.get("confidence", "provisional"),
        }
    return out


def load_preprocessed(source_file: str) -> dict[str, dict]:
    path = PREPROC_DIR / source_file
    if not path.exists():
        raise FileNotFoundError(f"Preprocessed file missing: {path}")
    posts = json.loads(path.read_text(encoding="utf-8"))
    return {p["post_id"]: p for p in posts}


def load_topic_outputs(univ_code: str) -> dict:
    base = TOPIC_DIR / univ_code
    if not base.exists():
        raise FileNotFoundError(f"Topic outputs missing for {univ_code}: {base}")

    def _load(name):
        f = base / f"{name}.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    return {
        "assignments": _load("topic_assignments"),
        "labels": _load("topic_labels"),
        "keywords": _load("topic_keywords"),
        "metadata": _load("topic_metadata"),
        "rep_docs": _load("topic_rep_docs"),
        "topics_over_time": _load("topics_over_time"),
        "umap_2d": _load("umap_2d"),
    }


def load_vad_scores(univ_code: str) -> dict[str, dict]:
    """Aggregate per-researcher JSONL files. Latest scored_at per post_id wins."""
    out: dict[str, dict] = {}
    if not VAD_DIR.exists():
        return out
    for researcher_dir in VAD_DIR.iterdir():
        if not researcher_dir.is_dir():
            continue
        jsonl_path = researcher_dir / f"{univ_code}_vad_scores.jsonl"
        if not jsonl_path.exists():
            continue
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            pid = rec.get("post_id")
            if not pid:
                continue
            prev = out.get(pid)
            if prev and prev.get("scored_at", "") >= rec.get("scored_at", ""):
                continue
            out[pid] = rec
    return out


def safe_ts(unix: int | None) -> int | None:
    if not isinstance(unix, (int, float)):
        return None
    unix = int(unix)
    if unix < TS_MIN_VALID or unix > TS_MAX_VALID:
        return None
    return unix


def build_univ_record(univ_code: str, mapping: dict) -> tuple[dict, dict]:
    """Returns (institutional_doc, research_doc)."""
    info = mapping[univ_code]
    posts_by_id = load_preprocessed(info["source_file"])
    topic = load_topic_outputs(univ_code)
    vad = load_vad_scores(univ_code)

    assignments = topic["assignments"] or []
    labels_list = topic["labels"] or []
    keywords_dict = topic["keywords"] or {}
    metadata = topic["metadata"] or {}
    umap_dict = topic["umap_2d"] or {}

    label_by_id = {item["topic_id"]: item.get("label", f"Topic {item['topic_id']}") for item in labels_list}

    # Build flat post records aligned with topic_assignments order (so umap_xy aligns).
    posts_out = []
    topic_buckets: dict[int, list[dict]] = defaultdict(list)
    invalid_ts_count = 0
    vad_scored = 0

    for a in assignments:
        pid = a["post_id"]
        src = posts_by_id.get(pid)
        if not src:
            continue
        ts = safe_ts(src.get("timestamp_unix"))
        if ts is None and src.get("timestamp_unix") is not None:
            invalid_ts_count += 1
        v = vad.get(pid, {})
        has_vad = "V" in v and "A" in v and "D" in v
        if has_vad:
            vad_scored += 1
        topic_id = a.get("topic_id", -1)
        rec = {
            "post_id": pid,
            "text": src.get("text", ""),
            "ts": ts,
            "lang": src.get("language_detected"),
            "topic_id": topic_id,
            "topic_label": label_by_id.get(topic_id, "Noise" if topic_id == -1 else f"Topic {topic_id}"),
            "V": v.get("V") if has_vad else None,
            "A": v.get("A") if has_vad else None,
            "D": v.get("D") if has_vad else None,
            "sarcasm": v.get("sarcasm") if has_vad else None,
            "flags": v.get("flags") if has_vad else [],
        }
        posts_out.append(rec)
        topic_buckets[topic_id].append(rec)

    post_count = len(posts_out)
    vad_coverage = (vad_scored / post_count) if post_count else 0.0

    # Per-topic aggregates
    topics_out = []
    for tid, bucket in sorted(topic_buckets.items()):
        scored = [p for p in bucket if p["V"] is not None]
        n = len(bucket)
        s = len(scored)
        topics_out.append({
            "id": tid,
            "label": label_by_id.get(tid, "Noise" if tid == -1 else f"Topic {tid}"),
            "size": n,
            "scored": s,
            "mean_V": round(sum(p["V"] for p in scored) / s, 2) if s else None,
            "mean_A": round(sum(p["A"] for p in scored) / s, 2) if s else None,
            "mean_D": round(sum(p["D"] for p in scored) / s, 2) if s else None,
            "sarcasm_rate": round(sum(1 for p in scored if p.get("sarcasm")) / s, 3) if s else None,
            "keywords": [{"word": kw["word"], "score": round(kw["score"], 4)} for kw in (keywords_dict.get(str(tid)) or [])[:10]],
        })

    # Date range
    valid_ts = [p["ts"] for p in posts_out if p["ts"] is not None]
    date_range = None
    if valid_ts:
        date_range = [
            datetime.fromtimestamp(min(valid_ts), tz=timezone.utc).strftime("%Y-%m-%d"),
            datetime.fromtimestamp(max(valid_ts), tz=timezone.utc).strftime("%Y-%m-%d"),
        ]

    base = {
        "univ_code": univ_code,
        "school_alias": info["school_alias"],
        "region": info["region"],
        "post_count": post_count,
        "topic_count": len(topics_out),
        "vad_coverage": round(vad_coverage, 4),
        "date_range": date_range,
        "invalid_ts_count": invalid_ts_count,
        "topics": topics_out,
        "topics_over_time": topic["topics_over_time"] or {},
        "metadata": {
            "n_outliers": metadata.get("n_outliers"),
            "outlier_rate": metadata.get("outlier_rate"),
            "npmi": metadata.get("npmi"),
            "silhouette": metadata.get("silhouette"),
        },
        "posts": posts_out,
    }

    # Research variant: append UMAP coords aligned with posts[] order
    research = dict(base)
    if umap_dict and isinstance(umap_dict, dict) and "coords" in umap_dict:
        coords_by_id = umap_dict["coords"]
        research["umap_xy"] = [coords_by_id.get(p["post_id"]) for p in posts_out]
        research["umap_present"] = True
    else:
        research["umap_xy"] = None
        research["umap_present"] = False

    return base, research


def build_all(target_univs: list[str] | None = None):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "institutional").mkdir(exist_ok=True)
    (OUT_DIR / "research").mkdir(exist_ok=True)

    mapping = load_mapping()
    if target_univs:
        univs = [u for u in target_univs if u in mapping]
    else:
        univs = sorted(mapping.keys())

    summary = []
    meta = []
    for univ in univs:
        print(f"[ETL] Building {univ}...", flush=True)
        try:
            inst, research = build_univ_record(univ, mapping)
        except FileNotFoundError as e:
            print(f"[ETL] SKIP {univ}: {e}", file=sys.stderr)
            continue

        (OUT_DIR / "institutional" / f"{univ}.json").write_text(
            json.dumps(inst, ensure_ascii=False), encoding="utf-8"
        )
        (OUT_DIR / "research" / f"{univ}.json").write_text(
            json.dumps(research, ensure_ascii=False), encoding="utf-8"
        )

        info = mapping[univ]
        summary.append({
            "univ_code": univ,
            "school_alias": info["school_alias"],
            "region": info["region"],
            "post_count": inst["post_count"],
            "topic_count": inst["topic_count"],
            "vad_coverage": inst["vad_coverage"],
            "date_range": inst["date_range"],
            "umap_present": research["umap_present"],
            "topics_top3": [t["label"] for t in sorted(inst["topics"], key=lambda x: -x["size"])[:3]],
        })
        meta.append({
            "univ_code": univ,
            "school_alias": info["school_alias"],
            "region": info["region"],
            "source_file": info["source_file"],
            "confidence": info["confidence"],
            "vad_coverage": inst["vad_coverage"],
            "umap_present": research["umap_present"],
        })

    (OUT_DIR / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ETL] Done. {len(summary)} universities written to {OUT_DIR}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--univ", action="append", help="Specific university code(s) to build")
    args = ap.parse_args()
    build_all(args.univ)


if __name__ == "__main__":
    main()
