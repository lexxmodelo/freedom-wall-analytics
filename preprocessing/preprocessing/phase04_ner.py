"""Phase 04: NER-based anonymization.

Three layers:
1. spaCy en_core_web_lg PERSON spans → [REDACTED_NAME]
2. Curated Tagalog given-name list → [REDACTED_NAME]
3. Title heuristic (Sir/Maam/Prof/Dr/Engr/Atty + capitalized name) → [PROFESSOR_NAME]
4. Department keywords / acronyms → [DEPARTMENT]

spaCy is loaded lazily because the model is ~500 MB and not always installed.
If spaCy isn't available, the pipeline still runs — layers 2/3/4 still fire.
The QC report records whether spaCy was active.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import re

from .name_lists import (
    DEPARTMENT_ACRONYM_PATTERN,
    DEPARTMENT_PATTERNS,
    load_given_names,
)
from .regex_lib import PATTERNS
from .schools import REGION_TAGS

log = logging.getLogger(__name__)

# Phase02-emitted region tags can be mangled by spaCy NER if they fall inside
# a PERSON span (observed: "Jollibee [CARAGA]" → spaCy spans into the opening
# bracket and leaves "[REDACTED_NAME]CARAGA]" — orphan closing bracket).
# Mask each region tag with a single-token sentinel before NER, restore after.
_REGION_TAG_PATTERN = re.compile(
    r'\[(?:' + '|'.join(re.escape(r) for r in REGION_TAGS) + r')\]'
)


def _mask_region_tags(text: str) -> tuple[str, list[str]]:
    """Replace each '[REGION]' with an opaque sentinel spaCy won't span.

    Returns (masked_text, captured_tags_in_order).
    """
    captured: list[str] = []

    def _grab(m: re.Match[str]) -> str:
        captured.append(m.group(0))
        # Single underscored ALL-CAPS token reads as one OOV token to spaCy
        # and rarely gets tagged as PERSON/ORG.
        return f"REGIONTAG{len(captured)}MASK"

    masked = _REGION_TAG_PATTERN.sub(_grab, text)
    return masked, captured


def _unmask_region_tags(text: str, captured: list[str]) -> str:
    for i, tag in enumerate(captured, start=1):
        text = text.replace(f"REGIONTAG{i}MASK", tag)
    return text


@lru_cache(maxsize=1)
def _load_spacy() -> Any | None:
    """Load spaCy lazily; return None if the model isn't available."""
    try:
        import spacy  # type: ignore
    except ImportError:
        log.warning("spaCy not installed; NER layer 1 disabled")
        return None
    try:
        nlp = spacy.load("en_core_web_lg")
    except OSError:
        log.warning(
            "spaCy model en_core_web_lg not found; "
            "run `python -m spacy download en_core_web_lg`. NER layer 1 disabled."
        )
        return None
    return nlp


def _redact_persons_spacy(text: str, nlp: Any) -> str:
    """Replace PERSON spans with [REDACTED_NAME] using offset-based slicing.

    Iterating in reverse keeps earlier spans' offsets valid as we splice.
    """
    doc = nlp(text)
    spans = sorted(
        (ent for ent in doc.ents if ent.label_ == "PERSON"),
        key=lambda e: e.start_char,
        reverse=True,
    )
    for ent in spans:
        text = text[: ent.start_char] + "[REDACTED_NAME]" + text[ent.end_char:]
    return text


def _redact_persons_namelist(text: str, names_pattern) -> str:
    return names_pattern.sub("[REDACTED_NAME]", text)


def _redact_professor(text: str) -> str:
    return PATTERNS["professor_title"].sub("[PROFESSOR_NAME]", text)


def _redact_department(text: str) -> str:
    for p in DEPARTMENT_PATTERNS:
        text = p.sub("[DEPARTMENT]", text)
    text = DEPARTMENT_ACRONYM_PATTERN.sub("[DEPARTMENT]", text)
    return text


def redact(text: str, names_pattern, nlp: Any | None) -> str:
    # Mask phase02 region tags before NER so spaCy can't span into them.
    text, captured_tags = _mask_region_tags(text)
    if nlp is not None:
        text = _redact_persons_spacy(text, nlp)
    text = _redact_persons_namelist(text, names_pattern)
    text = _redact_professor(text)
    text = _redact_department(text)
    text = _unmask_region_tags(text, captured_tags)
    return text


def run(posts: Iterable[dict], names_path: Path):
    _, names_pattern = load_given_names(str(names_path))
    nlp = _load_spacy()
    for post in posts:
        if post is None:
            yield None
            continue
        post["text"] = redact(post["text"], names_pattern, nlp)
        yield post
