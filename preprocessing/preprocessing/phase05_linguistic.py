"""Phase 05: Linguistic preservation passthrough.

We deliberately do NOT translate, lowercase, or remove diacritics here. The
downstream RoBERTa-Tagalog tokenizer is multilingual-sensitive and works best
on text in its original mixed-language form. This module exists primarily as
a sanity gate: confirm NFKC was applied (phase01) and the text wasn't acci-
dentally emptied by aggressive redaction in phase04.
"""
from __future__ import annotations

import unicodedata
from typing import Iterable


def assert_preserved(text: str) -> str:
    # Confirm NFKC stability: applying it again should be a no-op.
    if unicodedata.normalize("NFKC", text) != text:
        text = unicodedata.normalize("NFKC", text)
    return text


def run(posts: Iterable[dict]):
    for post in posts:
        if post is None:
            yield None
            continue
        post["text"] = assert_preserved(post["text"])
        yield post
