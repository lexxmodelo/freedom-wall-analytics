"""Compiled regex library shared across phases.

School-specific replacement patterns are NOT here — they're built at runtime
from configs/schools.yaml in schools.py. This module holds only generic
patterns used by phases 03/04/08/10.
"""
from __future__ import annotations

import re

PATTERNS: dict[str, re.Pattern[str]] = {
    # ----- Phase 02 (school anonymization) supplementary -----
    # Generic Freedom Wall indexing hashtag — covers any school's variant
    # because the orchestrator strips these before per-school replacement.
    "indexing_hashtag":
        re.compile(r'(?i)#[A-Z]{2,8}(?:FW|FreedomWall|Files)\d*'),

    # Catch-all hashtag stripper. Run AFTER per-school anonymization (which
    # has already replaced known school-related hashtags with region tags),
    # so this only sweeps up residual campaign/sports tags like #UAAPSeason88,
    # #DLSU, #AnimoLaSalle that survived the per-school pass.
    "any_hashtag":
        re.compile(r'#\w+'),

    # ----- Phase 03 (noise reduction) -----
    # Strip the literal "Submitted:" word wherever it appears. Trailing
    # signatures (e.g. "Submitted: Anonymous student") have the word stripped
    # but the signature text remains for phase04 NER to redact if it's a name.
    "submitted_prefix":
        re.compile(r'\bSubmitted\s*:\s*', re.IGNORECASE),
    "see_more":
        re.compile(r'\.{3,}\s*See\s*more\b', re.IGNORECASE),
    "ellipsis_trail":
        re.compile(r'\s*\.{3,}\s*$'),
    "url":
        re.compile(
            r'https?://\S+'
            r'|www\.\S+'
            r'|\b\S+\.(?:com|net|org|ph|edu)(?:/\S*)?',
            re.IGNORECASE,
        ),
    "email":
        re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b'),
    # PH phone formats: +63xxxxxxxxxx, 09xxxxxxxxx, (02) 8xxx-xxxx
    "phone_ph":
        re.compile(
            r'(?:\+?63|0)9\d{2}[-\s]?\d{3}[-\s]?\d{4}'
            r'|\(0?2\)\s*\d{3,4}[-\s]?\d{4}'
        ),
    # Standalone digit run (4+ digits not part of a larger word)
    "student_id":
        re.compile(r'(?<!\w)\d{4,}(?!\w)'),
    # 4+ repeated chars -> exactly 3 (preserves emphasis like "sooo bad")
    "char_repeat":
        re.compile(r'(.)\1{3,}'),
    "whitespace":
        re.compile(r'\s+'),
    # Surrogate-pair garbage that survives faulty UTF-8 decoding
    "lone_surrogate":
        re.compile(r'[\ud800-\udfff]'),

    # ----- Phase 04 (NER heuristic) -----
    "professor_title":
        re.compile(
            r"\b(?:Sir|Ma'?am|Prof(?:essor)?|Dr|Engr|Atty)\.?\s+"
            r"([A-Z][a-zA-Zàáéíóúñ]+(?:\s+[A-Z][a-zA-Zàáéíóúñ]+){0,2})"
        ),

    # ----- Phase 08 (timestamps) -----
    "tz_suffix":
        re.compile(
            r'\s+(?:HKT|PHT|GMT[+-]\d+|UTC[+-]\d+|PST|PHST|SGT)\s*$',
            re.IGNORECASE,
        ),

    # ----- Phase 10 (quality gate) -----
    "pure_media":
        re.compile(
            r'^\s*(?:\[photo\]|\[video\]|\[image\]|\[REDACTED_NAME\])?\s*$',
            re.IGNORECASE,
        ),
}


def char_repeat_collapse(text: str) -> str:
    """Collapse 4+ repeated chars to exactly 3."""
    return PATTERNS["char_repeat"].sub(r'\1\1\1', text)
