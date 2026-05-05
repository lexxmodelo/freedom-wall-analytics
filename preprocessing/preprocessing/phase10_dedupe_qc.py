"""Phase 10: Deduplication, quality gate, regional bucketing, QC report.

This is the only phase that materializes posts in memory (everything before
streams). Necessary because near-dup detection is a global operation.
"""
from __future__ import annotations

import hashlib
import logging
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

from .regex_lib import PATTERNS
from .schools import REGION_TAGS, SchoolsConfig

log = logging.getLogger(__name__)

MIN_CHARS = 10


def _post_hash(text: str) -> str:
    """Lowercased SHA-256 of cleaned text. Mirrors scraper_project.utils.post_hash."""
    return hashlib.sha256(text.lower().strip().encode("utf-8")).hexdigest()


def _try_load_minhash():
    """Lazy import of datasketch; return None if unavailable."""
    try:
        from datasketch import MinHash, MinHashLSH  # type: ignore
        return MinHash, MinHashLSH
    except ImportError:
        log.warning("datasketch not installed; near-dup detection disabled")
        return None


def _shingles(text: str, k: int = 3) -> list[str]:
    """Word-level k-gram shingles, lowercased and punctuation-stripped."""
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    if len(words) < k:
        return [" ".join(words)] if words else []
    return [" ".join(words[i : i + k]) for i in range(len(words) - k + 1)]


def near_dedupe(posts: list[dict], threshold: float = 0.9, num_perm: int = 128) -> tuple[list[dict], int]:
    """Drop near-duplicates (Jaccard >= threshold), keep earliest.

    Returns (kept_posts, dropped_count). When datasketch isn't installed,
    returns the input unchanged.
    """
    mod = _try_load_minhash()
    if mod is None:
        return posts, 0
    MinHash, MinHashLSH = mod

    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    kept: list[dict] = []
    dropped = 0

    for idx, post in enumerate(posts):
        sh = _shingles(post["text"])
        if not sh:
            kept.append(post)
            continue
        m = MinHash(num_perm=num_perm)
        for s in sh:
            m.update(s.encode("utf-8"))
        if lsh.query(m):
            dropped += 1
            continue
        lsh.insert(str(idx), m)
        kept.append(post)
    return kept, dropped


def quality_gate(post: dict) -> tuple[bool, str | None]:
    """Return (keep, rejection_reason)."""
    text = post.get("text", "")
    if PATTERNS["pure_media"].fullmatch(text):
        return False, "pure_media"
    # Strip placeholder tokens before checking length so a post that's
    # nothing but [REDACTED_NAME] doesn't pass via length alone.
    bare = re.sub(r"\[(?:REDACTED_NAME|PROFESSOR_NAME|DEPARTMENT|"
                  r"Metro Manila|Luzon/Provincial|Baguio/Benguet)\]",
                  "", text).strip()
    if len(bare) < MIN_CHARS:
        return False, "too_short"
    return True, None


def assign_region(post: dict, cfg: SchoolsConfig) -> str | None:
    """Pick the post's region — ALWAYS from the source JSONL file.

    One Freedom Wall = one region. The post's origin (which JSONL it was
    scraped from) is the only authoritative signal. School names mentioned
    in the post body are *discourse content* — they tell us what the post
    talks about, not where the post is from. A UPD student writing about
    UPB friends still belongs in Metro Manila.

    `_phase02_regions` is retained for QC reporting (counting posts that
    mention schools from regions other than their own) but never used here.
    """
    code = post.get("_source_code")
    if not code:
        return None
    return cfg.scraper_code_to_region.get(code)


def finalize(posts: list[dict], cfg: SchoolsConfig) -> tuple[dict[str, list[dict]], dict, list[tuple[dict, str]]]:
    """Bucket posts by source_code (one bucket per Freedom Wall = batch
    unit for downstream BERTopic + topic labelling), strip internal fields,
    return QC stats.

    Each post retains its `region` field so cross-regional aggregation at
    analysis time is a simple groupby; no information is lost by bucketing
    per-school instead of per-region.

    Returns (buckets, qc_stats, rejections_with_reason).
    """
    buckets: dict[str, list[dict]] = {}
    rejections: list[tuple[dict, str]] = []

    source_counts: Counter[str] = Counter()
    region_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    mentions_other_region = 0  # post mentions a school from a different region
    mentions_own_region_only = 0
    mentions_no_school = 0
    timestamp_missing = 0

    for post in posts:
        keep, why = quality_gate(post)
        if not keep:
            rejections.append((post, why or "quality_gate"))
            continue

        region = assign_region(post, cfg)
        if region is None:
            rejections.append((post, "no_region_assignable"))
            continue

        source_code = post.get("_source_code")
        if not source_code:
            rejections.append((post, "no_source_code"))
            continue

        # Discourse-content stats: what regions does the TEXT reference,
        # relative to the post's own (source-derived) region?
        text_regions = set(post.get("_phase02_regions") or [])
        if not text_regions:
            mentions_no_school += 1
        elif text_regions == {region}:
            mentions_own_region_only += 1
        else:
            mentions_other_region += 1

        if post.get("timestamp_unix") is None:
            timestamp_missing += 1

        source_counts[source_code] += 1
        region_counts[region] += 1
        language_counts[post.get("language_detected", "Unknown")] += 1

        # Project to the final output schema. `source_code` is the
        # anonymized scraper code (FW-01, SLU, ...) — already in the
        # filename but kept inline so flattened/merged datasets retain
        # batch attribution. `region` lets analysis groupby cross-school.
        final = {
            "post_id": post.get("post_id"),
            "source_code": source_code,
            "text": post["text"],
            "engagement": post.get("engagement", {"reactions": 0, "comments": 0, "shares": 0}),
            "timestamp_unix": post.get("timestamp_unix"),
            "region": region,
            "language_detected": post.get("language_detected", "Unknown"),
        }
        buckets.setdefault(source_code, []).append(final)

    qc = {
        "total_kept": sum(source_counts.values()),
        "total_rejected": len(rejections),
        "by_source": dict(source_counts),
        "by_region": dict(region_counts),
        "by_language": dict(language_counts),
        # Discourse-content metrics (do NOT affect routing — region is
        # always from source). Useful for understanding cross-school
        # discourse patterns.
        "text_mentions_no_school": mentions_no_school,
        "text_mentions_own_region_only": mentions_own_region_only,
        "text_mentions_other_region": mentions_other_region,
        "timestamp_missing": timestamp_missing,
    }
    return buckets, qc, rejections
