"""Pipeline orchestrator.

Reads JSONL files from `input_dir`, runs phases 01→10 in order, writes three
region-bucketed JSON files plus _qc_report.json and _rejected.jsonl.

Order of phases differs slightly from numeric order: NER (phase04) runs
BEFORE noise reduction (phase03) so spaCy keeps the casing/punctuation it
needs for entity recall. The phase numbers reflect methodology grouping; the
runtime order reflects pipeline correctness. See plan §Top 5 risks.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import (
    phase01_select,
    phase02_anonymize_school,
    phase03_noise_regex,
    phase04_ner,
    phase05_linguistic,
    phase06_stopwords,
    phase07_engagement,
    phase08_timestamps,
    phase09_language,
    phase10_dedupe_qc,
)
from .io_utils import (
    append_rejected,
    dump_qc_report,
    load_jsonl,
    reset_file,
    write_json,
)
from .schools import SchoolsConfig, build_replacement_table, load_schools

log = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    input_dir: Path
    output_dir: Path
    schools_path: Path
    tagalog_names_path: Path
    stopwords_dir: Path                 # holds stopwords_<language>.txt files
    limit: int | None = None
    phases: set[int] = field(default_factory=lambda: set(range(1, 11)))
    near_dup_threshold: float = 0.9


def _source_code_from_filename(path: Path) -> str:
    """Derive the scraper source code (FW-01, SLU, ...) from the JSONL stem."""
    return path.stem


def _stream_with_limit(stream: Iterable, limit: int | None) -> Iterable:
    if limit is None:
        yield from stream
        return
    for i, item in enumerate(stream):
        if i >= limit:
            return
        yield item


def run_pipeline(cfg: PipelineConfig) -> dict[str, Any]:
    """Execute the pipeline end-to-end. Returns the QC report as a dict."""
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    rejected_path = cfg.output_dir / "_rejected.jsonl"
    qc_path = cfg.output_dir / "_qc_report.json"
    reset_file(rejected_path)
    reset_file(qc_path)

    # Load configs
    schools_cfg: SchoolsConfig = load_schools(cfg.schools_path)
    table = build_replacement_table(schools_cfg)
    log.info(
        "Loaded %d schools, %d replacement rules",
        len(schools_cfg.schools), len(table),
    )

    # Discover input files
    jsonl_paths = sorted(cfg.input_dir.glob("*.jsonl"))
    log.info("Discovered %d JSONL files in %s", len(jsonl_paths), cfg.input_dir)

    # Aggregate input streams across files; tag each post with its source code.
    all_posts: list[dict] = []
    files_summary: list[dict] = []
    for path in jsonl_paths:
        code = _source_code_from_filename(path)
        # Don't process files that aren't in our scraper_code_to_region map —
        # they may be auxiliary outputs (e.g. *_session.json renamed to .jsonl)
        if code not in schools_cfg.scraper_code_to_region:
            log.warning("Skipping %s: source code %r not in schools.yaml mapping", path.name, code)
            continue

        n_in = 0
        n_kept_phase1 = 0
        for raw_post in _stream_with_limit(load_jsonl(path), cfg.limit):
            n_in += 1
            selected, original = next(phase01_select.run([raw_post], code))
            if selected is None:
                append_rejected(rejected_path, original, "empty_text", "phase01")
                continue
            n_kept_phase1 += 1
            all_posts.append(selected)
        files_summary.append({"file": path.name, "code": code, "in": n_in, "kept_phase1": n_kept_phase1})
        log.info("%s: %d posts in, %d kept after phase01", path.name, n_in, n_kept_phase1)

    # ---- Phase 02: anonymize ----
    if 2 in cfg.phases:
        all_posts = list(phase02_anonymize_school.run(all_posts, schools_cfg, table))

    # ---- Phase 04: NER (BEFORE phase03 to preserve casing for spaCy) ----
    if 4 in cfg.phases:
        all_posts = list(phase04_ner.run(all_posts, cfg.tagalog_names_path))

    # ---- Phase 03: noise regex ----
    if 3 in cfg.phases:
        all_posts = list(phase03_noise_regex.run(all_posts))

    # ---- Phase 05: linguistic preservation ----
    if 5 in cfg.phases:
        all_posts = list(phase05_linguistic.run(all_posts))

    # ---- Phase 06: stopword flagging ----
    if 6 in cfg.phases:
        all_posts = list(phase06_stopwords.run(all_posts, cfg.stopwords_dir))

    # ---- Phase 07: engagement ----
    if 7 in cfg.phases:
        all_posts = list(phase07_engagement.run(all_posts))

    # ---- Phase 08: timestamps ----
    if 8 in cfg.phases:
        all_posts = list(phase08_timestamps.run(all_posts))

    # ---- Phase 09: language ----
    if 9 in cfg.phases:
        all_posts = list(phase09_language.run(all_posts))

    # ---- Phase 10: exact dedup + near-dup + bucket + write ----
    # Exact dedup (across regions) first — duplicates of cleaned text are
    # genuine duplicates regardless of source.
    seen: set[str] = set()
    deduped: list[dict] = []
    exact_drops = 0
    for post in all_posts:
        h = phase10_dedupe_qc._post_hash(post["text"])
        if h in seen:
            append_rejected(rejected_path, post, "exact_duplicate", "phase10")
            exact_drops += 1
            continue
        seen.add(h)
        deduped.append(post)
    log.info("Exact dedup: dropped %d / %d", exact_drops, len(all_posts))

    near_drops = 0
    if 10 in cfg.phases:
        deduped, near_drops = phase10_dedupe_qc.near_dedupe(
            deduped, threshold=cfg.near_dup_threshold,
        )
        log.info("Near dedup: dropped %d (Jaccard >= %.2f)", near_drops, cfg.near_dup_threshold)

    # Note: regional Philippine languages (Cebuano, Ilokano, Kapampangan,
    # Waray, Hiligaynon) are no longer dropped here. They get explicit
    # language_detected labels in phase09 and are kept in output so
    # cross-regional cultural/linguistic analysis can compare them.
    buckets, qc_stats, rejections = phase10_dedupe_qc.finalize(deduped, schools_cfg)

    for post, reason in rejections:
        append_rejected(rejected_path, post, reason, "phase10")

    # Write one file per source / Freedom Wall — these are the BATCH UNITS
    # for downstream BERTopic + topic labelling. Filenames use the scraper
    # code (`FW-01_cleaned.json`, `SLU_cleaned.json`) which is already an
    # anonymized identifier per scraper_project/config.py. Each post still
    # carries its `region` field, so cross-regional aggregation at analysis
    # time is a simple groupby — no information lost by bucketing per-school.
    for source_code in sorted(buckets):
        source_posts = buckets[source_code]
        if not source_posts:
            continue
        out = cfg.output_dir / f"{source_code}_cleaned.json"
        write_json(out, source_posts)
        log.info("%s: %d posts -> %s", source_code, len(source_posts), out.name)

    # Compose QC report
    report: dict[str, Any] = {
        "input_files": files_summary,
        "exact_duplicates_dropped": exact_drops,
        "near_duplicates_dropped": near_drops,
        **qc_stats,
        "schools_loaded": [s.canonical_acronym for s in schools_cfg.schools],
        "phases_executed": sorted(cfg.phases),
        "near_dup_threshold": cfg.near_dup_threshold,
    }
    dump_qc_report(qc_path, report)
    log.info("QC report -> %s", qc_path.name)
    return report
