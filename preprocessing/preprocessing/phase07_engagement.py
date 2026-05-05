"""Phase 07: Engagement normalization.

Coerce reactions/comments/shares to non-negative ints. Handles the rare
"1.2K" / "2M" string forms by rounding (the scraper already converts most
to ints, but defensive parsing here costs little).
"""
from __future__ import annotations

import re
from typing import Iterable

_K = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[Kk]\s*$")
_M = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[Mm]\s*$")


def _coerce(v) -> int:
    if v is None:
        return 0
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return max(0, int(v))
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return 0
        m = _K.match(s)
        if m:
            return int(round(float(m.group(1)) * 1000))
        m = _M.match(s)
        if m:
            return int(round(float(m.group(1)) * 1_000_000))
        try:
            return max(0, int(float(s)))
        except ValueError:
            return 0
    return 0


def normalize_engagement(eng: dict | None) -> dict:
    eng = eng or {}
    return {
        "reactions": _coerce(eng.get("reactions")),
        "comments": _coerce(eng.get("comments")),
        "shares": _coerce(eng.get("shares")),
    }


def run(posts: Iterable[dict]):
    for post in posts:
        if post is None:
            yield None
            continue
        post["engagement"] = normalize_engagement(post.get("engagement"))
        yield post
