"""Hard assertion: no school identifier survives in output JSON files.

Run after a smoke pass. Tests are skipped if output/ doesn't exist yet.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

# Patterns that must NEVER appear in any output post `text`. Add more as the
# corpus grows. Each pattern represents a different school's identifying
# signal — the regional tag should have replaced it.
LEAK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'\b(?:Ateneo|ADMU|Katipunan|Loyola Heights|Blue Eagles?|Halikinu)\b', re.IGNORECASE),
    re.compile(r'\b(?:UPD(?:iliman)?|Diliman|Sunken Garden|AS Walk)\b', re.IGNORECASE),
    re.compile(r'\b(?:DLSU|De La Salle|La Salle|Taft Avenue|Green Archers|Animo)\b', re.IGNORECASE),
    re.compile(r'\b(?:FEU|Far Eastern|Morayta|Tamaraws?|Nicanor Reyes)\b', re.IGNORECASE),
    re.compile(r'\b(?:PUP|Sta\.\s*Mesa|Mabini Campus)\b', re.IGNORECASE),
    re.compile(r'\b(?:UPLB|Los\s*Ba(?:ñ|n)os|Mt\.?\s*Makiling|Aggies)\b', re.IGNORECASE),
    re.compile(r'\b(?:LPU-?B|Lyceum)\b', re.IGNORECASE),
    re.compile(r'\b(?:CSU|Caraga State|Cagayan State|Ampayon|Butuan)\b', re.IGNORECASE),
    re.compile(r'\b(?:UPB|Governor Pack)\b', re.IGNORECASE),
    re.compile(r'\b(?:BSU|Benguet State|La Trinidad|Mountaineers)\b', re.IGNORECASE),
    re.compile(r'\b(?:UB|University of Baguio|Cardinals)\b'),
    re.compile(r'\b(?:SLU|Saint Louis|Maryheights|Bonifacio St|Navigators)\b', re.IGNORECASE),
    re.compile(r'#\w*(?:FW|FreedomWall|Files)\w*\d*'),
]

# Some patterns inevitably collide with non-school usage (e.g. "UP" as in
# "what's up", "UB" as a verb). Allow a configured exception list. Phase02
# protects 'UP' with a strict word-boundary so this should be empty in
# normal runs.
ALLOWLIST = re.compile(
    r'\[(?:Metro Manila|Luzon/Provincial|Baguio/Benguet|REDACTED_NAME|PROFESSOR_NAME|DEPARTMENT)\]'
)


@pytest.mark.parametrize("filename", [
    "metro_manila_posts.json",
    "luzon_provincial_posts.json",
    "baguio_benguet_posts.json",
])
def test_no_leak_in_output(filename):
    path = OUTPUT_DIR / filename
    if not path.exists():
        pytest.skip(f"{filename} not yet generated; run pipeline first")
    posts = json.loads(path.read_text(encoding="utf-8"))
    leaks: list[tuple[str, str, str]] = []
    for post in posts:
        text = post.get("text", "")
        # Mask the legal placeholder tags first so we don't false-positive on them
        masked = ALLOWLIST.sub("[TAG]", text)
        for pat in LEAK_PATTERNS:
            for m in pat.finditer(masked):
                leaks.append((post.get("post_id", "?"), pat.pattern, m.group(0)))
    assert not leaks, (
        f"Found {len(leaks)} school-identifier leaks in {filename}. First 5: "
        + str(leaks[:5])
    )
