"""Retry NIM labeling for topics that have label='Unlabeled' (API_GIVEUP) in
an existing run. Reuses cached keywords + representative docs so no
re-clustering is needed. Useful after rate-limit storms.

Usage:
    python -m topic_modeling.retry_labels --researcher alexx
    python -m topic_modeling.retry_labels --researcher alexx --univ MM-PSEC-1

The retry uses the SAME effective_rpm from the researcher config — so make
sure you've lowered it (e.g. to 25) before running, or the retry will hit
the same 429 storms.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import labeling, temporal
from .dotenv import autoload as autoload_dotenv
from .io_utils import load_json, write_json
from .logging_setup import log_action, setup_logger

log = setup_logger("retry_labels")


def find_unlabeled_topics(univ_dir: Path) -> list[int]:
    labels_path = univ_dir / "topic_labels.json"
    if not labels_path.exists():
        return []
    labels = load_json(labels_path)
    return [r["topic_id"] for r in labels
            if r.get("label") == "Unlabeled"
            or "API_GIVEUP" in r.get("flags", [])
            or "MALFORMED_OUTPUT" in r.get("flags", [])]


def retry_labels_for_university(
    *,
    root: Path,
    univ_code: str,
    researcher_cfg: dict,
    prompt_template: str,
    acronyms: dict[str, str] | None,
    cache_dir: Path,
) -> dict:
    """Re-label every Unlabeled topic in this university. Returns stats."""
    univ_dir = root / "outputs" / univ_code
    if not univ_dir.exists():
        log.warning("No outputs for %s — skipping", univ_code)
        return {"univ_code": univ_code, "skipped": True}

    unlabeled = find_unlabeled_topics(univ_dir)
    if not unlabeled:
        log.info("%s: no Unlabeled topics; skipping", univ_code)
        return {"univ_code": univ_code, "n_retried": 0, "n_recovered": 0}

    log.info("%s: %d unlabeled topics to retry", univ_code, len(unlabeled))
    keywords = load_json(univ_dir / "topic_keywords.json")
    rep_docs = load_json(univ_dir / "topic_rep_docs.json")
    labels = load_json(univ_dir / "topic_labels.json")
    labels_by_id = {r["topic_id"]: r for r in labels}

    api_key = os.environ[researcher_cfg["api_key_env_var"]]
    rate_limiter = labeling.TokenBucket(researcher_cfg.get("effective_rpm", 25))
    client = labeling.NimClient(
        api_key=api_key,
        endpoint=researcher_cfg["model_endpoint"],
        model_id=researcher_cfg["model_id"],
        temperature=researcher_cfg["temperature"],
        max_tokens=researcher_cfg["max_tokens"],
        request_timeout=researcher_cfg["request_timeout_seconds"],
        max_retries=researcher_cfg["max_retries"],
        backoff_min=researcher_cfg["retry_backoff_min_seconds"],
        backoff_max=researcher_cfg["retry_backoff_max_seconds"],
        rate_limiter=rate_limiter,
    )

    n_recovered = 0
    n_still_failed = 0
    try:
        for tid in unlabeled:
            kw_entries = keywords.get(str(tid), [])
            kw_words = [e["word"] for e in kw_entries] if kw_entries else []
            rd = rep_docs.get(str(tid), [])
            old_rec = labels_by_id.get(tid, {})
            old_sig = old_rec.get("temporal_signature") or old_rec.get("_temporal") or {}
            temporal_hint = (temporal.format_date_range(old_sig.get("concentrated_months", []))
                             if old_sig.get("is_event_driven") else None)

            log.info("Retrying %s/topic %d (n_keywords=%d, n_rep=%d)",
                     univ_code, tid, len(kw_words), len(rd))
            new_rec = labeling.label_topic(
                client, prompt_template,
                univ_code=univ_code, topic_id=tid,
                keywords=kw_words, rep_docs=rd,
                cache_dir=cache_dir,
                acronyms=acronyms or None,
                temporal_hint=temporal_hint,
            )
            if new_rec["label"] == "Unlabeled":
                n_still_failed += 1
                log.warning("  still failed: %s", new_rec.get("flags"))
            else:
                n_recovered += 1
                # Preserve metadata fields that the original run set on this record
                new_rec["temporal_signature"] = old_sig
                if old_rec.get("flags") and "EVENT_DRIVEN" in old_rec["flags"]:
                    new_rec.setdefault("flags", []).append("EVENT_DRIVEN")
                labels_by_id[tid] = new_rec
                log.info("  -> %r", new_rec["label"])
    finally:
        client.close()

    if n_recovered > 0:
        # Write back the updated labels list (in original topic_id order)
        new_labels = [labels_by_id[r["topic_id"]] for r in labels]
        write_json(univ_dir / "topic_labels.json", new_labels)

    return {
        "univ_code": univ_code,
        "n_retried": len(unlabeled),
        "n_recovered": n_recovered,
        "n_still_failed": n_still_failed,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="topic_modeling.retry_labels", description=__doc__)
    p.add_argument("--researcher", required=True)
    p.add_argument("--univ", default=None,
                   help="Optional: retry only this single univ_code. Default: all assigned.")
    p.add_argument("--root", default=None)
    args = p.parse_args(argv)

    here = Path(__file__).resolve().parent
    root = Path(args.root).resolve() if args.root else here.parent
    autoload_dotenv(root)

    researcher_cfg = load_json(root / "configs" / f"{args.researcher}.json")
    prompt_template = (root / "configs" / "prompts" / "labeling_prompt.txt").read_text(encoding="utf-8")
    mapping = load_json(root / "configs" / "university_mapping.yaml") if False else None  # YAML not JSON
    # Load mapping via yaml
    import yaml
    with (root / "configs" / "university_mapping.yaml").open("r", encoding="utf-8") as f:
        mapping = yaml.safe_load(f)
    cache_dir = root / "api_cache" / "labeling_responses"

    if args.univ:
        univ_codes = [args.univ]
    else:
        univ_codes = []
        for fname, m in mapping.get("mappings", {}).items():
            if fname in researcher_cfg.get("assigned_files", []):
                if m.get("active") and m.get("code"):
                    univ_codes.append(m["code"])

    summary = []
    for code in univ_codes:
        acronyms = labeling.load_acronyms_for_university(root / "configs", code)
        result = retry_labels_for_university(
            root=root, univ_code=code,
            researcher_cfg=researcher_cfg,
            prompt_template=prompt_template,
            acronyms=acronyms,
            cache_dir=cache_dir,
        )
        summary.append(result)

    log_action(
        root / "action_log.md",
        action_type="LABEL_RETRY",
        title=f"Retry labels for {args.researcher} ({len(univ_codes)} universities)",
        action="Re-ran NIM labeling for any topic with label='Unlabeled' or API_GIVEUP/MALFORMED_OUTPUT flags.",
        configuration={"effective_rpm": researcher_cfg.get("effective_rpm")},
        outputs=summary,
    )
    print()
    print("=" * 60)
    for r in summary:
        if r.get("skipped"):
            print(f"  {r['univ_code']:14s}  SKIPPED")
        else:
            print(f"  {r['univ_code']:14s}  retried={r['n_retried']}  recovered={r['n_recovered']}  still_failed={r['n_still_failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
