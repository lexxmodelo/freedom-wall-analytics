"""Centralized logging for the preprocessing pipeline.

Mirrors the style of scraper_project/utils.py:setup_logger so log output looks
consistent across the two projects. Logs go to both stderr and a per-run file.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PHT = timezone(timedelta(hours=8), name="Asia/Manila")

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s"


def setup_logger(name: str, log_dir: Path | None = None) -> logging.Logger:
    """Create or return a configured logger.

    Idempotent: repeated calls with the same name reuse the existing handlers.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    fmt = logging.Formatter(_FORMAT)

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(PHT).strftime("%Y%m%d_%H%M%S")
        fh = logging.FileHandler(log_dir / f"preprocessing_{stamp}.log", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.propagate = False
    return logger
