"""Text preparation applied BEFORE TF-IDF / embedding / NIM rep-doc submission.

The preprocessing phase replaces person names, campus locations, departments,
regions, etc. with bracket-tagged placeholders (e.g., [REDACTED_NAME], [CAR],
[DEPARTMENT]). Those placeholders are pure noise for topic modeling — they
appear in 79% of SLU posts and dominate cluster keyword extraction. Strip
them before vectorization.

Audit (SLU, 2026-05-05): 6 placeholder types found —
  [REDACTED_NAME] (13,867)  [CAR] (604)  [DEPARTMENT] (75)
  [NCR] (5)  [PROFESSOR_NAME] (3)  [ANNOUNCEMENT] (1)

The generic regex catches future placeholder types from preprocessing
without requiring a code change here.
"""
from __future__ import annotations

import re

# Match any bracket-tagged token of capital letters/digits/underscores.
# Examples: [REDACTED_NAME], [CAR], [DEPARTMENT], [PROFESSOR_NAME]
_PLACEHOLDER_RE = re.compile(r"\[[A-Z][A-Z0-9_]*\]")

# Match runs of whitespace (left over after placeholder removal).
_WS_RE = re.compile(r"\s+")


def strip_placeholders(text: str) -> str:
    """Remove all bracket-tagged anonymization placeholders and collapse whitespace."""
    if not text:
        return text
    cleaned = _PLACEHOLDER_RE.sub(" ", text)
    return _WS_RE.sub(" ", cleaned).strip()


def strip_placeholders_batch(texts: list[str]) -> list[str]:
    return [strip_placeholders(t) for t in texts]


def count_placeholders(text: str) -> int:
    """Used by diagnostics / action_log entries."""
    if not text:
        return 0
    return len(_PLACEHOLDER_RE.findall(text))
