"""Phase 02: Aggressive school-name anonymization.

Replaces every identifier of every university with one of three regional tags.
Ordering of replacements is enforced by schools.build_replacement_table — see
plan §Anonymization order.

Side-product: the function also reports which rule labels matched, which the
orchestrator uses to detect cross-university posts and to fall back to a
source-code region tag when no rule matched at all.
"""
from __future__ import annotations

import re
from typing import Iterable

from .schools import REGION_TAGS, ReplacementRule, SchoolsConfig

# After all replacements run, collapse consecutive duplicate region tags
# ("[NCR] [NCR]" → "[NCR]") because phrases like "ADMU and Ateneo" produce
# them naturally.
_TAG_REPEAT = re.compile(
    r'(\[(?:' + '|'.join(re.escape(r) for r in REGION_TAGS) + r')\])'
    r'(?:\s+\1)+'
)


def anonymize(text: str, table: list[ReplacementRule]) -> tuple[str, set[str], set[str]]:
    """Apply each replacement rule in order.

    Returns (anonymized_text, set_of_matched_labels, set_of_matched_regions).
    `matched_regions` lets the orchestrator detect cross-university posts.
    """
    matched_labels: set[str] = set()
    matched_regions: set[str] = set()

    for pattern, replacement, label in table:
        if pattern.search(text):
            matched_labels.add(label)
            # The replacement string carries the region tag (or empty for
            # ambiguous mascots / dropped location stamps).
            text = pattern.sub(replacement, text)
            if replacement.startswith("[") and replacement.endswith("]"):
                matched_regions.add(replacement.strip("[]"))

    text = _TAG_REPEAT.sub(r'\1', text)
    return text, matched_labels, matched_regions


def run(posts: Iterable[dict], cfg: SchoolsConfig, table: list[ReplacementRule]):
    """Stream over posts, mutate `text` in place, attach phase02 metadata."""
    for post in posts:
        if post is None:
            yield None
            continue
        anon_text, labels, regions = anonymize(post["text"], table)
        post["text"] = anon_text
        post["_phase02_labels"] = sorted(labels)
        post["_phase02_regions"] = sorted(regions)
        yield post
