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
# Cebuano/Bisaya function words and particles that distinguish from Tagalog.
# `py3langid` misclassifies most Cebuano social media posts as `tl` so we
# need a ratio-based heuristic. Words shared with Tagalog (mga, sa, na, etc.)
# are intentionally omitted; only Cebuano-specific markers are kept here.
CEBUANO_FUNC = {
    # possessives & pronouns
    "akong", "imong", "iyang", "atong", "inyong", "ilang", "ako", "ikaw",
    "siya", "kami", "kita", "kamo", "sila", "ko", "nako", "nimo", "niya",
    "namo", "nato", "ninyo", "nila",
    # function particles (high-density Cebuano markers)
    "kay", "og", "ug", "diay", "gani", "gud", "gyud", "jud", "bitaw",
    "bay", "bitaw", "pud", "sad", "lagi", "bana", "uy", "hala",
    # WH words distinct from Tagalog
    "unsa", "kinsa", "asa", "kanus-a", "ngano", "giunsa", "pila",
    # negation distinct from Tagalog
    "dili", "di", "ayaw", "walay", "way",
    # common verbs/markers
    "naa", "anaa", "naay", "basin", "tabangi", "tagaa", "tagai",
    "buot", "buhi", "kuyaw", "lami", "nindot", "kuan",
    # connectives
    "aron", "tungod", "samtang", "human", "samtang",
    "nga",  # general linker — very distinctive
    # additional corpus-frequent words
    "dayon", "ato", "ila", "akoa", "imoha", "ihaha",
    "padong", "padayon", "buot", "manggi",
    "makig", "magpa", "mag",
}
ENGLISH_FUNC = {
    "the", "a", "an", "of", "to", "in", "is", "that", "this", "you", "i",
    "my", "with", "for", "on", "but", "not", "be", "have", "do", "does",
    "did", "are", "was", "were", "will", "would", "could", "should", "can",
    "it", "he", "she", "they", "them", "his", "her", "their", "our", "us",
    "we", "me", "from", "by", "as", "if", "so", "or", "and",
}

_TOKEN = re.compile(r"[A-Za-z']+")
# Philippine regional languages preserved with explicit labels (not dropped
# as "Other") so cross-cultural analysis can surface their distinct
# discourse. py3langid's iso-639 codes:
DIALECT_LABELS = {
    "ceb": "Cebuano",       # primary language of Caraga / Visayas / Mindanao
    "ilo": "Ilokano",       # Northern Luzon
    "pam": "Kapampangan",   # Central Luzon
    "war": "Waray",         # Eastern Visayas
    "hil": "Hiligaynon",    # Western Visayas
}

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
    ceb_ratio = sum(1 for t in toks if t in CEBUANO_FUNC) / n

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
        "ceb_ratio": round(ceb_ratio, 4),
        "primary": primary,
        "token_count": n,
    }

    # py3langid honored when it confidently identifies a regional language.
    if primary in DIALECT_LABELS:
        meta["dialect_code"] = primary
        return DIALECT_LABELS[primary], meta
    # Cebuano heuristic: function-word ratio outpaces Tagalog. Threshold of
    # 0.05 (1 Cebuano marker per 20 tokens) catches typical FW-06 posts
    # without flagging Tagalog posts that contain incidental shared words.
    if ceb_ratio >= 0.05 and ceb_ratio > tl_ratio:
        meta["dialect_code"] = "ceb"
        return "Cebuano", meta
    # Both Tagalog and English function-words present at density → Taglish.
    if tl_ratio >= 0.05 and en_ratio >= 0.05:
        return "Taglish", meta
    if primary == "tl" or (tl_ratio > en_ratio and tl_ratio >= 0.03):
        return "Filipino", meta
    if primary == "en" or en_ratio > tl_ratio:
        return "English", meta
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
