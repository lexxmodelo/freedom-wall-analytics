"""Phase 06: Stopword flagging (no removal).

Per Section 3.3.5 of the methodology, pragmatic particles are flagged
here for downstream BERTopic c-TF-IDF removal — NOT removed at this
stage. The cleaned-corpus output drops the `_stopword_flags` field;
researchers running BERTopic separately can recompute counts from the
cleaned text using these same per-language stopword files.

The flag dict is structured as `{language_label: {token: count}}` so
downstream consumers can apply language-specific stopword removal:
when running BERTopic on the Mindanao subset, load the Cebuano + Tagalog
+ English files; on Metro Manila, load only Tagalog + English; etc.

Languages auto-discovered from files matching `stopwords_*.txt`.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from .io_utils import load_text_lines

_TOKEN = re.compile(r"[A-Za-z'-]+")
_STOPWORDS_FILE = re.compile(r"^stopwords_([a-z]+)\.txt$", re.IGNORECASE)


@lru_cache(maxsize=4)
def _load_stopword_bundle(stopwords_dir_str: str) -> tuple[tuple[str, frozenset[str]], ...]:
    """Discover and load all `stopwords_<language>.txt` files in a directory.

    Returns a tuple of (language_label, words) pairs (tuple instead of dict
    so it's hashable for the lru_cache).
    """
    p = Path(stopwords_dir_str)
    bundles: list[tuple[str, frozenset[str]]] = []
    if not p.exists():
        return tuple()
    for f in sorted(p.glob("stopwords_*.txt")):
        m = _STOPWORDS_FILE.match(f.name)
        if not m:
            continue
        lang = m.group(1).lower()
        words = frozenset(w.lower() for w in load_text_lines(f))
        if words:
            bundles.append((lang, words))
    return tuple(bundles)


def flag(text: str, bundles: tuple[tuple[str, frozenset[str]], ...]) -> dict[str, dict[str, int]]:
    """Per-language counts of stopword occurrences in `text`."""
    toks = [t for t in _TOKEN.findall(text.lower())]
    if not toks:
        return {}
    out: dict[str, dict[str, int]] = {}
    for lang, words in bundles:
        counts: dict[str, int] = {}
        for tok in toks:
            if tok in words:
                counts[tok] = counts.get(tok, 0) + 1
        if counts:
            out[lang] = counts
    return out


def run(posts: Iterable[dict], stopwords_dir: Path):
    bundles = _load_stopword_bundle(str(stopwords_dir))
    for post in posts:
        if post is None:
            yield None
            continue
        post["_stopword_flags"] = flag(post["text"], bundles)
        yield post
