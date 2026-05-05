"""Phase 09: Language detection — English / Filipino / Taglish / Other.

Strategy: function-word ratio over Tagalog and English closed-class words +
py3langid as a tiebreaker. Empirically the ratio test is more reliable than
any off-the-shelf detector for short, code-switched social media posts.

py3langid is optional; if it's not installed we fall back to ratio-only.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

log = logging.getLogger(__name__)

TAGALOG_FUNC = {
    "ang", "ng", "mga", "sa", "ay", "na", "at", "kasi", "talaga", "naman",
    "lang", "din", "rin", "yung", "ito", "ako", "ikaw", "siya", "kami",
    "tayo", "kayo", "sila", "po", "opo", "hindi", "oo", "wala", "may",
    "yan", "yun", "ba", "eh", "pala", "daw", "raw", "ano", "kung", "para",
    "bakit", "kaya", "gusto", "ayoko", "talagang", "kahit", "pero", "ngunit",
}
ENGLISH_FUNC = {
    "the", "a", "an", "of", "to", "in", "is", "that", "this", "you", "i",
    "my", "with", "for", "on", "but", "not", "be", "have", "do", "does",
    "did", "are", "was", "were", "will", "would", "could", "should", "can",
    "it", "he", "she", "they", "them", "his", "her", "their", "our", "us",
    "we", "me", "from", "by", "as", "if", "so", "or", "and",
}

_TOKEN = re.compile(r"[A-Za-z']+")
_REGIONAL_DIALECTS = {"ilo", "pam", "ceb", "war", "hil"}

_LANGID = None


def _load_langid():
    global _LANGID
    if _LANGID is not None:
        return _LANGID
    try:
        import py3langid as langid  # type: ignore
        _LANGID = langid
    except ImportError:
        log.warning("py3langid not installed; using ratio-only detection")
        _LANGID = False
    return _LANGID


def detect(text: str) -> tuple[str, dict]:
    """Return (label, meta).

    Labels: 'English' | 'Filipino' | 'Taglish' | 'Other'
    `meta` carries tl_ratio, en_ratio, primary, dialect_flag (when applicable).
    """
    toks = _TOKEN.findall(text.lower())
    n = len(toks)
    if n < 4:
        return "Unknown", {"token_count": n}

    tl_ratio = sum(1 for t in toks if t in TAGALOG_FUNC) / n
    en_ratio = sum(1 for t in toks if t in ENGLISH_FUNC) / n

    primary = None
    langid = _load_langid()
    if langid:
        try:
            primary, _conf = langid.classify(text)
        except Exception:  # noqa: BLE001
            primary = None

    meta = {
        "tl_ratio": round(tl_ratio, 4),
        "en_ratio": round(en_ratio, 4),
        "primary": primary,
        "token_count": n,
    }

    # Both function-word families present at meaningful density → Taglish.
    if tl_ratio >= 0.05 and en_ratio >= 0.05:
        return "Taglish", meta
    if primary == "tl" or (tl_ratio > en_ratio and tl_ratio >= 0.03):
        return "Filipino", meta
    if primary == "en" or en_ratio > tl_ratio:
        return "English", meta
    if primary in _REGIONAL_DIALECTS:
        meta["dialect_flag"] = primary
        return "Other", meta
    return "Other", meta


def run(posts: Iterable[dict]):
    for post in posts:
        if post is None:
            yield None
            continue
        label, meta = detect(post["text"])
        post["language_detected"] = label
        post["_lang_meta"] = meta
        yield post
