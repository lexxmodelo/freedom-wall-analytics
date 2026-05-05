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
from .schools import SchoolsConfig

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
    """Pick the post's region.

    Strategy:
    1. If phase02 matched exactly one region, use that.
    2. If phase02 matched multiple regions (cross-uni post), use the first
       (sorted alphabetically — deterministic) and flag.
    3. If phase02 matched zero regions, fall back to the scraper-code map.
    4. If still unknown, return None — orchestrator will reject the post.
    """
    regions = post.get("_phase02_regions") or []
    if len(regions) == 1:
        return regions[0]
    if len(regions) > 1:
        return sorted(regions)[0]
    code = post.get("_source_code")
    return cfg.scraper_code_to_region.get(code) if code else None


def finalize(posts: list[dict], cfg: SchoolsConfig) -> tuple[dict[str, list[dict]], dict, list[tuple[dict, str]]]:
    """Bucket posts by region, strip internal fields, return QC stats.

    Returns (buckets, qc_stats, rejections_with_reason).
    """
    buckets: dict[str, list[dict]] = {
        "Metro Manila": [],
        "Luzon/Provincial": [],
        "Baguio/Benguet": [],
    }
    rejections: list[tuple[dict, str]] = []

    region_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    cross_uni = 0
    fallback_region = 0
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

        if not post.get("_phase02_regions"):
            fallback_region += 1
        if len(post.get("_phase02_regions") or []) > 1:
            cross_uni += 1
        if post.get("timestamp_unix") is None:
            timestamp_missing += 1

        region_counts[region] += 1
        language_counts[post.get("language_detected", "Unknown")] += 1

        # Project to the final output schema. Drop everything starting with
        # underscore plus the raw timestamp/url fields that should not appear
        # in the published corpus.
        final = {
            "post_id": post.get("post_id"),
            "text": post["text"],
            "engagement": post.get("engagement", {"reactions": 0, "comments": 0, "shares": 0}),
            "timestamp_unix": post.get("timestamp_unix"),
            "region": region,
            "language_detected": post.get("language_detected", "Unknown"),
        }
        buckets[region].append(final)

    qc = {
        "total_kept": sum(region_counts.values()),
        "total_rejected": len(rejections),
        "by_region": dict(region_counts),
        "by_language": dict(language_counts),
        "cross_university_posts": cross_uni,
        "region_via_source_fallback": fallback_region,
        "timestamp_missing": timestamp_missing,
    }
    return buckets, qc, rejections
