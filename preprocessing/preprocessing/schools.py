"""School-config loader and replacement-table builder.

Reads configs/schools.yaml into typed dataclasses and composes the ordered
list of (compiled regex, replacement) tuples that phase02 applies. Ordering
is critical — see plan §Anonymization order — so we preserve it explicitly
rather than relying on Python's sort stability.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REGION_TAGS = {
    "Metro Manila": "[Metro Manila]",
    "Luzon/Provincial": "[Luzon/Provincial]",
    "Baguio/Benguet": "[Baguio/Benguet]",
}


@dataclass
class LocationMarker:
    phrase: str
    semantic_replace: bool = True


@dataclass
class School:
    canonical_acronym: str
    full_name_variations: list[str]
    freedom_wall_hashtag_pattern: str
    scraper_code: str | None
    location_markers: list[LocationMarker] = field(default_factory=list)
    mascot_cheer_terms: list[str] = field(default_factory=list)
    region: str = ""
    data_confidence: str = "low"

    @property
    def region_tag(self) -> str:
        return REGION_TAGS[self.region]


@dataclass
class SchoolsConfig:
    schools: list[School]
    ambiguous_mascots: list[str]
    generic_location_allowlist: list[str]
    scraper_code_to_region: dict[str, str]


def load_schools(path: Path) -> SchoolsConfig:
    """Parse configs/schools.yaml into a SchoolsConfig."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    schools: list[School] = []
    for s in raw.get("schools", []):
        markers = [
            LocationMarker(
                phrase=m["phrase"],
                semantic_replace=bool(m.get("semantic_replace", True)),
            )
            for m in (s.get("location_markers") or [])
        ]
        schools.append(
            School(
                canonical_acronym=s["canonical_acronym"],
                full_name_variations=list(s.get("full_name_variations") or []),
                freedom_wall_hashtag_pattern=s["freedom_wall_hashtag_pattern"],
                scraper_code=s.get("scraper_code"),
                location_markers=markers,
                mascot_cheer_terms=list(s.get("mascot_cheer_terms") or []),
                region=s["region"],
                data_confidence=s.get("data_confidence", "low"),
            )
        )

    return SchoolsConfig(
        schools=schools,
        ambiguous_mascots=list(raw.get("ambiguous_mascots") or []),
        generic_location_allowlist=list(raw.get("generic_location_allowlist") or []),
        scraper_code_to_region=dict(raw.get("scraper_code_to_region") or {}),
    )


# ---------------------------------------------------------------------------
# Replacement-table builder (used by phase02)
# ---------------------------------------------------------------------------

# Each entry: (compiled regex, replacement_string, category_label).
# `category_label` is informational; the orchestrator logs counts per category
# for the QC report.
ReplacementRule = tuple[re.Pattern[str], str, str]


def build_replacement_table(cfg: SchoolsConfig) -> list[ReplacementRule]:
    """Compose the ordered list of (pattern, replacement, label) tuples.

    Order (most specific first → least specific last):
      1. Indexing hashtags
      2. Multi-word full names (longest first)
      3. Two-word names (UP Diliman, UP Baguio) → handled within group 2
      4. Location markers (semantic_replace inline; non-semantic dropped)
      5. Mascot/cheer phrases (ambiguous ones become deletion)
      6. Single-word school names
      7. Acronyms (longest first; short ones with strict word boundaries)
    """
    rules: list[ReplacementRule] = []

    # 1. Indexing hashtags (per-school regex from YAML)
    for s in cfg.schools:
        rules.append((
            re.compile(s.freedom_wall_hashtag_pattern),
            s.region_tag,
            f"hashtag:{s.canonical_acronym}",
        ))

    # 2 + 3. Full name variations (multi-word and single-word together,
    # ordered by length descending so e.g. "Ateneo de Manila University"
    # matches before bare "Ateneo").
    name_entries: list[tuple[str, str, str]] = []  # (phrase, region_tag, label)
    for s in cfg.schools:
        for name in s.full_name_variations:
            name_entries.append((name, s.region_tag, f"name:{s.canonical_acronym}"))
    name_entries.sort(key=lambda e: -len(e[0]))
    for phrase, tag, label in name_entries:
        rules.append((
            re.compile(rf'(?<!\w){re.escape(phrase)}(?!\w)', re.IGNORECASE),
            tag,
            label,
        ))

    # 4. Location markers
    loc_entries: list[tuple[str, str, str, bool]] = []
    for s in cfg.schools:
        for m in s.location_markers:
            loc_entries.append((m.phrase, s.region_tag, f"loc:{s.canonical_acronym}", m.semantic_replace))
    loc_entries.sort(key=lambda e: -len(e[0]))
    for phrase, tag, label, semantic in loc_entries:
        # See plan §Linguistic-preserve rule. Non-semantic markers are simply
        # dropped (replacement = ""); semantic markers become the region tag.
        replacement = tag if semantic else ""
        rules.append((
            re.compile(rf'(?<!\w){re.escape(phrase)}(?!\w)', re.IGNORECASE),
            replacement,
            label,
        ))

    # 5. Mascot/cheer phrases
    ambiguous = {m.lower() for m in cfg.ambiguous_mascots}
    mascot_entries: list[tuple[str, str, str]] = []
    for s in cfg.schools:
        for term in s.mascot_cheer_terms:
            if term.lower() in ambiguous:
                continue  # handled separately below as deletion
            mascot_entries.append((term, s.region_tag, f"mascot:{s.canonical_acronym}"))
    mascot_entries.sort(key=lambda e: -len(e[0]))
    for phrase, tag, label in mascot_entries:
        rules.append((
            re.compile(rf'(?<!\w){re.escape(phrase)}(?!\w)', re.IGNORECASE),
            tag,
            label,
        ))

    # 5b. Ambiguous mascots: drop entirely (no region attribution)
    for am in cfg.ambiguous_mascots:
        rules.append((
            re.compile(rf'(?<!\w){re.escape(am)}(?!\w)', re.IGNORECASE),
            "",
            f"ambiguous_mascot:{am}",
        ))

    # 6. Bare acronyms — longest first, strict word boundaries.
    acronym_entries: list[tuple[str, str, str]] = []
    for s in cfg.schools:
        ac = s.canonical_acronym
        acronym_entries.append((ac, s.region_tag, f"acro:{ac}"))
    acronym_entries.sort(key=lambda e: -len(e[0]))
    for ac, tag, label in acronym_entries:
        # Disallow the acronym being preceded by # (already handled hashtag),
        # by another word char, or followed by another word char. This stops
        # `UP` matching inside `UPLB` and stops `SLU` matching inside
        # `#SLUFreedomWall12345` (which is replaced earlier anyway, but be safe).
        # Case-insensitive because real posts use lowercase forms ("admu",
        # "slu", "uplb"). Word boundaries keep collateral damage minimal —
        # standalone lowercase "slu", "ub", etc. are rare enough in English/
        # Filipino that false positives are negligible.
        rules.append((
            re.compile(rf'(?<![#\w]){re.escape(ac)}(?!\w)', re.IGNORECASE),
            tag,
            label,
        ))

    return rules
