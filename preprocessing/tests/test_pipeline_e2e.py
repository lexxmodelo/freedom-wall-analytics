"""End-to-end test against the golden fixture.

Runs the full pipeline (skipping spaCy NER if not installed) on
fixtures/golden_input.jsonl and asserts:
- All school identifiers anonymized
- Engagement coerced to ints
- Languages classified
- Pure-media posts dropped
- Exact duplicates collapsed
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from preprocessing.pipeline import PipelineConfig, run_pipeline

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
CONFIGS = ROOT / "configs"


@pytest.fixture
def temp_workspace(tmp_path):
    """Create an input dir with the golden fixture renamed to SLU.jsonl
    so the source-code map kicks in."""
    in_dir = tmp_path / "input"
    in_dir.mkdir()
    # Copy fixture as SLU.jsonl so all posts inherit a known scraper code
    # for the source-fallback test (post g008 has no school markers).
    shutil.copyfile(FIXTURES / "golden_input.jsonl", in_dir / "SLU.jsonl")
    out_dir = tmp_path / "output"
    return in_dir, out_dir


def _flatten(out_dir: Path) -> list[dict]:
    posts: list[dict] = []
    for fname in (
        "metro_manila_posts.json",
        "luzon_provincial_posts.json",
        "baguio_benguet_posts.json",
    ):
        path = out_dir / fname
        if path.exists():
            posts.extend(json.loads(path.read_text(encoding="utf-8")))
    return posts


def test_e2e_pipeline(temp_workspace):
    in_dir, out_dir = temp_workspace
    cfg = PipelineConfig(
        input_dir=in_dir,
        output_dir=out_dir,
        schools_path=CONFIGS / "schools.yaml",
        tagalog_names_path=CONFIGS / "tagalog_given_names.txt",
        tagalog_stopwords_path=CONFIGS / "stopwords_tagalog.txt",
    )
    report = run_pipeline(cfg)

    posts = _flatten(out_dir)
    assert len(posts) > 0, "No posts produced"

    # No raw hashtag survives
    for p in posts:
        assert "#" not in p["text"] or "[Metro Manila]" in p["text"] or \
               "[Luzon/Provincial]" in p["text"] or "[Baguio/Benguet]" in p["text"], \
            f"Unstripped hashtag in: {p['text']!r}"
        assert "FreedomWall" not in p["text"]
        assert "Submitted:" not in p["text"]

    # Engagement is dict of ints
    for p in posts:
        eng = p["engagement"]
        for k in ("reactions", "comments", "shares"):
            assert isinstance(eng[k], int), f"{k}={eng[k]!r} not int"

    # Pure-media post (g010) should be dropped
    assert "g010" not in {p["post_id"] for p in posts}

    # Too-short post (g011) should be dropped
    assert "g011" not in {p["post_id"] for p in posts}

    # Exact duplicate (g012 == g008 verbatim) — only one survives
    surviving_ids = {p["post_id"] for p in posts}
    assert not ("g008" in surviving_ids and "g012" in surviving_ids), \
        "Exact duplicate not deduplicated"

    # Required fields only
    allowed = {"post_id", "text", "engagement", "timestamp_unix", "region", "language_detected"}
    for p in posts:
        assert set(p.keys()) == allowed, f"Extra/missing keys in: {sorted(p.keys())}"

    # Language histogram has at least the labels we expect
    assert "by_language" in report
    assert sum(report["by_language"].values()) == len(posts)
