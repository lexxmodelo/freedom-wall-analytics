"""Phase 08: Timestamp normalization.

Strip trailing TZ tokens (HKT/PHT/GMT+8/UTC+8/...), parse via
scraper_project/utils.parse_absolute_timestamp, fall back to timestamp_iso,
coerce to Asia/Manila, emit `timestamp_unix` as int epoch.

Many scraped posts have both timestamp_iso AND timestamp_raw set to null —
in that case we set timestamp_unix to null and let the QC report record it.
We do NOT reject the post; the user needs the texts even if timestamps are
missing.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .logging_setup import PHT
from .regex_lib import PATTERNS

log = logging.getLogger(__name__)

# Reuse scraper_project utilities. Fall back gracefully if the scraper folder
# isn't on sys.path (rare — the test harness adds it).
_SCRAPER_PARSER = None


def _load_scraper_parser():
    """Import scraper_project.utils.parse_absolute_timestamp lazily."""
    global _SCRAPER_PARSER
    if _SCRAPER_PARSER is not None:
        return _SCRAPER_PARSER
    research_root = Path(__file__).resolve().parents[2]
    scraper_path = research_root / "scraper_project"
    if str(research_root) not in sys.path:
        sys.path.insert(0, str(research_root))
    try:
        from scraper_project.utils import parse_absolute_timestamp  # type: ignore
        _SCRAPER_PARSER = parse_absolute_timestamp
    except ImportError:
        log.warning("scraper_project.utils not importable; using local fallback parser")
        _SCRAPER_PARSER = _local_parse
    return _SCRAPER_PARSER


def _local_parse(raw: str) -> datetime | None:
    """Best-effort fallback parser for the few formats we know."""
    fmts = [
        "%B %d, %Y %I:%M:%S %p",
        "%B %d, %Y %I:%M %p",
        "%b %d, %Y %I:%M %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _coerce_to_datetime(parsed) -> datetime | None:
    """The scraper utility returns ISO strings; the local fallback returns
    datetimes. Coerce either form to a tz-aware datetime in Asia/Manila."""
    if parsed is None:
        return None
    if isinstance(parsed, datetime):
        return parsed
    if isinstance(parsed, str):
        try:
            return datetime.fromisoformat(parsed)
        except ValueError:
            return None
    return None


def to_unix_pht(timestamp_raw, timestamp_iso) -> int | None:
    """Return an int Unix epoch in Asia/Manila, or None if unparseable.

    Handles three input shapes the scraper has used over time:
    - int Unix epoch in `timestamp_raw` (current scraper output)
    - human-readable date string in `timestamp_raw` (legacy scraper)
    - ISO-8601 string in `timestamp_iso` (preferred fallback)
    """
    # Fast path: timestamp_raw is already a Unix epoch.
    if isinstance(timestamp_raw, (int, float)) and timestamp_raw > 0:
        return int(timestamp_raw)
    # Some scraper versions stringify the epoch (e.g. "1777786481").
    if isinstance(timestamp_raw, str) and timestamp_raw.strip().isdigit():
        try:
            return int(timestamp_raw.strip())
        except ValueError:
            pass

    parse = _load_scraper_parser()

    candidates = [timestamp_iso, timestamp_raw]
    for raw in candidates:
        if not raw or not isinstance(raw, str):
            continue
        # Skip OCR'd image descriptions that some Facebook scrapes emit in
        # place of a real timestamp (e.g. "May be an image of...")
        if raw.lower().startswith("may be an image"):
            continue
        cleaned = PATTERNS["tz_suffix"].sub("", raw).strip()
        # Try the modern fromisoformat first — handles "2026-05-03T13:34:41+08:00"
        try:
            dt = datetime.fromisoformat(cleaned)
        except ValueError:
            dt = None
        if dt is None:
            dt = _coerce_to_datetime(parse(cleaned))
        if dt is None:
            dt = _coerce_to_datetime(_local_parse(cleaned))
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=PHT)
        else:
            dt = dt.astimezone(PHT)
        return int(dt.timestamp())
    return None


def run(posts: Iterable[dict]):
    for post in posts:
        if post is None:
            yield None
            continue
        post["timestamp_unix"] = to_unix_pht(
            post.get("timestamp_raw"),
            post.get("timestamp_iso"),
        )
        yield post
