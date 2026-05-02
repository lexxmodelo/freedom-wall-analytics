"""
Utility functions: logging, retry decorator, time helpers, deduplication.
"""

import hashlib
import logging
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

# ── Timezone ─────────────────────────────────────────────────────────────────
PHT = timezone(timedelta(hours=8))  # Asia/Manila


# ── Logging ──────────────────────────────────────────────────────────────────

def setup_logger(
    name: str = "fw_scraper",
    log_dir: str = "logs",
    level: int = logging.INFO,
) -> logging.Logger:
    """Create a logger that writes to both console and a timestamped file."""
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File
    ts = datetime.now(PHT).strftime("%Y%m%d_%H%M%S")
    fh = logging.FileHandler(
        os.path.join(log_dir, f"scrape_{ts}.log"), encoding="utf-8"
    )
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


# ── Sleep helpers ───────────────────────────────────────────────────────────

def random_sleep(lo: float, hi: float) -> None:
    """Sleep for a random duration between *lo* and *hi* seconds."""
    time.sleep(random.uniform(lo, hi))


# ── Timestamp helpers ────────────────────────────────────────────────────────

_RELATIVE_UNITS = {
    "s":  "seconds",
    "m":  "minutes",
    "h":  "hours",
    "d":  "days",
    "w":  "weeks",
    "mo": "months",
    "y":  "years",
    "sec": "seconds",
    "min": "minutes",
    "hr":  "hours",
}


def parse_relative_timestamp(raw: str) -> Optional[str]:
    """
    Convert Facebook-style relative timestamps ("3h", "2d", "1w") into
    approximate ISO-8601 strings anchored to *now*.

    Returns None if the string cannot be parsed.
    """
    raw = raw.strip().lower()
    if not raw:
        return None

    # "just now"
    if "just now" in raw or raw in ("now",):
        return datetime.now(PHT).isoformat()

    # "yesterday"
    if "yesterday" in raw:
        dt = datetime.now(PHT) - timedelta(days=1)
        return dt.isoformat()

    # Try "<number><unit>" patterns
    import re
    match = re.match(r"(\d+)\s*(s|sec|m|min|h|hr|d|w|mo|y)\b", raw)
    if not match:
        return None

    value = int(match.group(1))
    unit_key = match.group(2)
    unit = _RELATIVE_UNITS.get(unit_key)
    if not unit:
        return None

    now = datetime.now(PHT)
    if unit == "months":
        dt = now - timedelta(days=value * 30)
    elif unit == "years":
        dt = now - timedelta(days=value * 365)
    else:
        dt = now - timedelta(**{unit: value})

    return dt.isoformat()


def parse_absolute_timestamp(raw: str) -> Optional[str]:
    """
    Try common Facebook date formats and return ISO-8601.
    """
    formats = [
        "%B %d, %Y %I:%M:%S %p",  # "April 29, 2026 10:17:18 PM"
        "%B %d, %Y %I:%M %p",     # "April 29, 2026 10:17 PM"
        "%B %d, %Y at %I:%M %p",  # "April 28, 2026 at 2:30 PM"
        "%B %d, %Y",              # "April 28, 2026"
        "%b %d, %Y",              # "Apr 28, 2026"
        "%d %B %Y",               # "28 April 2026"
        "%Y-%m-%dT%H:%M:%S",      # ISO already
        "%m/%d/%Y",               # "04/28/2026"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            dt = dt.replace(tzinfo=PHT)
            return dt.isoformat()
        except ValueError:
            continue
    return None


def normalize_timestamp(raw: str) -> Optional[str]:
    """Try relative first, then absolute parsing."""
    result = parse_relative_timestamp(raw)
    if result:
        return result
    return parse_absolute_timestamp(raw)


def is_within_window(iso_ts: Optional[str], start: str, end: str) -> bool:
    """Check whether an ISO timestamp falls inside [start, end]."""
    if not iso_ts:
        return False
    try:
        dt = datetime.fromisoformat(iso_ts)
        s = datetime.fromisoformat(start).replace(tzinfo=PHT)
        e = datetime.fromisoformat(end).replace(tzinfo=PHT)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=PHT)
        return s <= dt <= e
    except (ValueError, TypeError):
        return False


# ── Deduplication ────────────────────────────────────────────────────────────

def post_hash(text: str) -> str:
    """SHA-256 of the stripped, lowered text — used for dedup."""
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def deduplicate_posts(posts: list[dict]) -> list[dict]:
    """Remove duplicate posts based on text hash, keeping the first occurrence."""
    seen: set[str] = set()
    unique: list[dict] = []
    for p in posts:
        h = post_hash(p.get("text", ""))
        if h not in seen:
            seen.add(h)
            p["post_id"] = h[:16]
            unique.append(p)
    return unique
