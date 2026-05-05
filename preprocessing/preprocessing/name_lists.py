"""Loader for the curated Tagalog given-name list.

Used by phase04 as a supplementary pass after spaCy NER. spaCy en_core_web_lg
catches English-orthographic Filipino names well; this list catches the
purely Filipino names spaCy tends to miss.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .io_utils import load_text_lines


@lru_cache(maxsize=4)
def load_given_names(path_str: str) -> tuple[set[str], re.Pattern[str]]:
    """Load given names + return a compiled word-boundary alternation regex.

    Cached because the regex compile cost is non-trivial when called per post.
    Returns (set of names for membership tests, compiled regex for matching).
    """
    names = set(load_text_lines(Path(path_str)))
    if not names:
        # Avoid creating a pattern that matches everything
        return names, re.compile(r"(?!x)x")
    # Sort longest first (so "Marie Antoinette" matches before "Marie")
    sorted_names = sorted(names, key=lambda n: -len(n))
    alt = "|".join(re.escape(n) for n in sorted_names)
    pattern = re.compile(rf"(?<!\w)(?:{alt})(?!\w)")
    return names, pattern


# Department/college keywords for [DEPARTMENT] redaction. These are signals
# of academic-unit identification that, while not as specific as a school
# name, would let a reader narrow down the school.
DEPARTMENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'\bDepartment of [A-Z][\w\s&-]{1,40}', re.IGNORECASE),
    re.compile(r'\bCollege of [A-Z][\w\s&-]{1,40}', re.IGNORECASE),
    re.compile(r'\bSchool of [A-Z][\w\s&-]{1,40}', re.IGNORECASE),
    re.compile(r'\bInstitute of [A-Z][\w\s&-]{1,40}', re.IGNORECASE),
]

# Department acronyms commonly seen in PH universities. Replaced with
# [DEPARTMENT]. Add more as the corpus reveals them — keep this list short
# enough that false positives stay low.
DEPARTMENT_ACRONYMS: set[str] = {
    "CSSP", "CHK", "CFA", "CSWCD", "CMC", "CSE", "CIT", "GCOE", "SAMCIS",
    "COE", "CBA", "CAS", "CEAT", "CFAD", "CITHM", "SOM", "SOL", "SOA",
    "SOE", "CEA", "CCS", "CTM", "CN", "COC",
}

DEPARTMENT_ACRONYM_PATTERN = re.compile(
    r'(?<![#\w])(?:' + '|'.join(re.escape(a) for a in sorted(DEPARTMENT_ACRONYMS, key=lambda x: -len(x))) + r')(?!\w)'
)
