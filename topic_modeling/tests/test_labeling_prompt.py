"""Snapshot test for the labeling prompt.

The exact wording is locked by methodology_changes.md:273-294. Any change to
configs/prompts/labeling_prompt.txt must be a deliberate methodology decision
documented in action_log.md and reflected in the snapshot below.
"""
from __future__ import annotations

from pathlib import Path

from topic_modeling.io_utils import sha256_text
from topic_modeling.labeling import parse_prompt, render_prompt


PROMPT_PATH = Path(__file__).resolve().parent.parent / "configs" / "prompts" / "labeling_prompt.txt"

EXPECTED_SUBSTRINGS = [
    "SYSTEM: You are an expert Data Analyst for Philippine universities.",
    "Taglish (Tagalog-English) social media posts",
    "Keywords: [KEYWORDS]",
    "Representative posts:",
    "[DOCUMENTS]",
    "Maximum 5 words",
    "Professional and descriptive",
    "In English",
    "If the posts are incoherent, spam, or lack a unifying theme, output exactly: Noise",
    "Output ONLY the label. No explanation, no punctuation, no quotes.",
]


def test_prompt_file_exists():
    assert PROMPT_PATH.exists(), f"Missing prompt file: {PROMPT_PATH}"


def test_prompt_contains_required_substrings():
    text = PROMPT_PATH.read_text(encoding="utf-8")
    for snippet in EXPECTED_SUBSTRINGS:
        assert snippet in text, f"Prompt missing required substring: {snippet!r}"


def test_prompt_renders_keywords_and_docs():
    template = PROMPT_PATH.read_text(encoding="utf-8")
    rendered = render_prompt(
        template,
        keywords=["finals", "stress", "ofw"],
        rep_docs=[
            {"text": "I cant sleep ang dami pa rin gagawin"},
            {"text": "huhu finals na bukas wala pa akong reviewer"},
        ],
    )
    assert "[KEYWORDS]" not in rendered
    assert "[DOCUMENTS]" not in rendered
    assert "finals, stress, ofw" in rendered


def test_prompt_parses_into_system_user():
    template = PROMPT_PATH.read_text(encoding="utf-8")
    rendered = render_prompt(template, keywords=["a"], rep_docs=[{"text": "x"}])
    msgs = parse_prompt(rendered)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "Philippine universities" in msgs[0]["content"]
    assert "Keywords:" in msgs[1]["content"]


def test_prompt_sha256_is_deterministic():
    text = PROMPT_PATH.read_text(encoding="utf-8")
    assert sha256_text(text) == sha256_text(text)
    assert len(sha256_text(text)) == 64
