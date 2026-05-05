"""Phase 06: Stopword flagging (no removal).

Per Section 3.3.5 of the methodology, pragmatic Tagalog particles are
removed downstream during BERTopic c-TF-IDF, NOT here. This phase only
attaches a per-post `_stopword_flags` count vector for the next stage.

The final output writer drops `_stopword_flags` so it doesn't appear in
the cleaned-corpus JSON files. Researchers running BERTopic separately can
recompute the counts from the cleaned text.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from .io_utils import load_text_lines

_TOKEN = re.compile(r"[A-Za-z']+")


@lru_cache(maxsize=4)
def _load_stopwords(path_str: str) -> frozenset[str]:
    return frozenset(w.lower() for w in load_text_lines(Path(path_str)))


def flag(text: str, stopwords: frozenset[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tok in _TOKEN.findall(text.lower()):
        if tok in stopwords:
            counts[tok] = counts.get(tok, 0) + 1
    return counts


def run(posts: Iterable[dict], stopwords_path: Path):
    sw = _load_stopwords(str(stopwords_path))
    for post in posts:
        if post is None:
            yield None
            continue
        post["_stopword_flags"] = flag(post["text"], sw)
        yield post
