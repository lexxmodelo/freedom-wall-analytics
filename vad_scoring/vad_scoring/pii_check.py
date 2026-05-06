"""Pre-API PII sweep — refuse to send any post with raw identifying material to NIM.

Checks (per methodology_changes.md §4.1; runs AFTER preprocessing's anonymization):
  - Raw email addresses
  - Raw Philippine mobile numbers (09\\d{9} or +639\\d{9})

Person-name detection is NOT done here — preprocessing's upstream NER + regex
pass already masks names as `[REDACTED_NAME]`. An earlier version of this module
included a "First Last" capitalized-bigram regex; an empirical test on CAR-PUB-1
(see action_log.md ACTION-003) found 100% of its hits were false positives
(e.g. "Freedom Wall", "Baguio City", "Comp Sci", "Studio Ghibli"). The check
provided zero safety value (real names were already masked) while rejecting 6.6%
of legitimate posts, so it was removed.

If preprocessing NER misses a name, that is a preprocessing bug to fix upstream,
not something to paper over with a brittle bigram heuristic at the API boundary.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PH_MOBILE_RE = re.compile(r"\b(?:\+?63|0)9\d{9}\b")


@dataclass
class PIIHit:
    kind: str           # "email" | "ph_mobile"
    match: str
    span: tuple[int, int]


def detect_pii(text: str) -> list[PIIHit]:
    """Return all PII hits in `text`. Empty list = clean."""
    hits: list[PIIHit] = []

    for m in _EMAIL_RE.finditer(text):
        hits.append(PIIHit("email", m.group(0), (m.start(), m.end())))

    for m in _PH_MOBILE_RE.finditer(text):
        hits.append(PIIHit("ph_mobile", m.group(0), (m.start(), m.end())))

    return hits


def is_clean(text: str) -> bool:
    """Quick yes/no check: True iff no PII detected."""
    return len(detect_pii(text)) == 0
