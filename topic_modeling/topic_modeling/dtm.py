"""Dynamic Topic Modeling — topics-over-time via BERTopic.topics_over_time().

Bins are monthly by default. Universities with <90 days of post history
produce <3 bins; the orchestrator logs a warning but does not fail.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .logging_setup import setup_logger

log = setup_logger(__name__)


def monthly_bin_count(timestamps_unix: list[int | None]) -> int:
    """How many distinct YYYY-MM buckets are present in non-null timestamps."""
    months: set[str] = set()
    for ts in timestamps_unix:
        if ts is None:
            continue
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        months.add(dt.strftime("%Y-%m"))
    return len(months)


def run_dtm(topic_model, docs: list[str], timestamps_unix: list[int | None],
            *, min_bins: int = 3) -> dict:
    """Run topics_over_time on the documents that have valid timestamps.

    Returns a dict ready to serialize as topics_over_time.json:
      {
        "n_bins": int,
        "skipped": bool,
        "skipped_reason": str | None,
        "n_docs_with_timestamps": int,
        "topics_over_time": [
            {"topic_id": int, "bin": "YYYY-MM-01", "frequency": int, "words": "..."},
            ...
        ]
      }
    """
    valid = [(d, ts) for d, ts in zip(docs, timestamps_unix) if ts is not None]
    n_valid = len(valid)
    n_bins = monthly_bin_count(timestamps_unix)
    if n_bins < min_bins:
        log.warning("DTM skipped: only %d monthly bins (<%d required)", n_bins, min_bins)
        return {
            "n_bins": n_bins,
            "skipped": True,
            "skipped_reason": f"only {n_bins} monthly bins available, need >= {min_bins}",
            "n_docs_with_timestamps": n_valid,
            "topics_over_time": [],
        }

    valid_docs = [d for d, _ in valid]
    valid_dts = [datetime.fromtimestamp(int(ts), tz=timezone.utc) for _, ts in valid]

    log.info("Running DTM on %d docs across %d monthly bins", n_valid, n_bins)
    df = topic_model.topics_over_time(
        docs=valid_docs,
        timestamps=valid_dts,
        nr_bins=n_bins,
    )
    records = []
    for _, row in df.iterrows():
        records.append({
            "topic_id": int(row["Topic"]),
            "bin": row["Timestamp"].strftime("%Y-%m-%d") if hasattr(row["Timestamp"], "strftime") else str(row["Timestamp"]),
            "frequency": int(row["Frequency"]),
            "words": str(row.get("Words", "")),
        })
    return {
        "n_bins": n_bins,
        "skipped": False,
        "skipped_reason": None,
        "n_docs_with_timestamps": n_valid,
        "topics_over_time": records,
    }
