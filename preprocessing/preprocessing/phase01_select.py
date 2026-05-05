"""Phase 01: Field selection + structural filtering.

- Drop everything except the seven fields we still need downstream.
- NFKC-normalize unicode early so phase02 regex matching is stable.
- Reject posts with empty/null/whitespace-only text.
- Carry a `_source_code` field forward (derived from the JSONL filename) so
  phase10 can apply the scraper-code → region fallback when text is generic.
"""
from __future__ import annotations

import unicodedata
from typing import Iterable, Iterator

KEEP_FIELDS = {
    "text",
    "timestamp_iso",
    "timestamp_raw",
    "engagement",
    "post_url",
    "post_id",
    "source",
}


def select_fields(post: dict, source_code: str) -> dict | None:
    """Project to KEEP_FIELDS, NFKC-normalize text, attach `_source_code`.

    Returns None when the post should be excluded (empty/null text). Caller
    handles logging to `_rejected.jsonl`.
    """
    text = post.get("text")
    if text is None:
        return None
    text = unicodedata.normalize("NFKC", str(text)).strip()
    if not text:
        return None

    out: dict = {k: post.get(k) for k in KEEP_FIELDS}
    out["text"] = text
    out["_source_code"] = source_code
    return out


def run(posts: Iterable[dict], source_code: str) -> Iterator[tuple[dict | None, dict]]:
    """Yield (selected_post_or_None, original_post) per input.

    The original is yielded alongside so the orchestrator can write rejections
    with their original payload preserved.
    """
    for post in posts:
        yield select_fields(post, source_code), post
