"""End-to-end test against the golden fixture.

The fixture's posts each carry a `_test_source_code` field indicating which
JSONL file they should be written to (because region routing is source-based,
each post's intended source matters).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from preprocessing.pipeline import PipelineConfig, run_pipeline

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
CONFIGS = ROOT / "configs"


@pytest.fixture
def temp_workspace(tmp_path):
    """Split fixture by `_test_source_code` into per-source JSONL files."""
    in_dir = tmp_path / "input"
    in_dir.mkdir()

    by_source: dict[str, list[str]] = defaultdict(list)
    with (FIXTURES / "golden_input.jsonl").open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            post = json.loads(line)
            code = post.pop("_test_source_code")
            by_source[code].append(json.dumps(post, ensure_ascii=False))

    for code, lines in by_source.items():
        (in_dir / f"{code}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    out_dir = tmp_path / "output"
    return in_dir, out_dir


def _flatten(out_dir: Path) -> dict[str, dict]:
    """Read all per-school output JSON files and return {post_id: post}."""
    by_id: dict[str, dict] = {}
    for path in sorted(out_dir.glob("*_cleaned.json")):
        for p in json.loads(path.read_text(encoding="utf-8")):
            by_id[p["post_id"]] = p
    return by_id


def test_e2e_pipeline(temp_workspace):
    in_dir, out_dir = temp_workspace
    cfg = PipelineConfig(
        input_dir=in_dir,
        output_dir=out_dir,
        schools_path=CONFIGS / "schools.yaml",
        tagalog_names_path=CONFIGS / "tagalog_given_names.txt",
        stopwords_dir=CONFIGS,
    )
    report = run_pipeline(cfg)
    posts = _flatten(out_dir)
    assert posts, "No posts produced"

    # ---- Source-based region routing ----
    # The bug being fixed: g015 (UPD post mentioning "upb baby") was being
    # routed to CAR because "upb" matched the UPB acronym rule.
    # Under source-only routing it must land in NCR.
    assert posts["g015"]["region"] == "NCR", (
        f"g015 (UPD source, mentions 'upb baby') should be NCR but "
        f"got {posts['g015']['region']}"
    )
    # Cross-school text mentions don't change the post's region.
    assert posts["g007"]["region"] == "NCR"          # FW-01 source, ADMU vs DLSU text
    assert posts["g004"]["region"] == "CALABARZON"   # FW-04 source
    assert posts["g005"]["region"] == "CAR"          # SLU source

    # UPOU mention still gets anonymized in the text.
    assert "UPOU" not in posts["g016"]["text"]
    assert "[CALABARZON]" in posts["g016"]["text"]

    # CARAGA region (CSU/Caraga) — separate analytical bucket.
    assert posts["g017"]["region"] == "CARAGA"
    # Bare "Caraga", "Butuan" are anonymized to [CARAGA]
    assert "Caraga" not in posts["g017"]["text"]
    assert "Butuan" not in posts["g017"]["text"]
    assert "[CARAGA]" in posts["g017"]["text"]
    # Submitted: ... timestamp line is fully stripped
    assert "Submitted" not in posts["g018"]["text"]
    assert "October" not in posts["g018"]["text"]
    assert "UTC" not in posts["g018"]["text"]
    # Cebuano content kept (not dropped as "Other")
    assert posts["g018"]["region"] == "CARAGA"

    # ---- Anonymization invariants ----
    for p in posts.values():
        # No raw indexing hashtag survives
        assert "FreedomWall" not in p["text"]
        assert "Submitted:" not in p["text"]
        # Engagement integers
        for k in ("reactions", "comments", "shares"):
            assert isinstance(p["engagement"][k], int)

    # ---- Drops & dedup ----
    assert "g010" not in posts  # pure-media
    assert "g011" not in posts  # too short
    # g012 is an exact duplicate of g008 — only one survives
    assert not ("g008" in posts and "g012" in posts)

    # ---- Schema enforcement ----
    allowed = {"post_id", "source_code", "text", "engagement", "timestamp_unix", "region", "language_detected"}
    for p in posts.values():
        assert set(p.keys()) == allowed, f"Extra/missing keys: {sorted(p.keys())}"

    # ---- Per-school batching ----
    # Each output file should contain only posts from a single source_code.
    for path in sorted(out_dir.glob("*_cleaned.json")):
        file_posts = json.loads(path.read_text(encoding="utf-8"))
        if not file_posts:
            continue
        codes = {p["source_code"] for p in file_posts}
        assert len(codes) == 1, f"{path.name} contains posts from multiple sources: {codes}"
        # Filename should match the source code
        expected = file_posts[0]["source_code"] + "_cleaned.json"
        assert path.name == expected, f"Filename {path.name} != source_code-derived {expected}"

    # ---- QC report sanity ----
    assert sum(report["by_language"].values()) == len(posts)
    assert "text_mentions_other_region" in report
    # g015 (UPD post mentioning UPB) and g007 (FW-01 mentioning DLSU within
    # same NCR region — wouldn't count) — at least g015 mentions
    # other region.
    assert report["text_mentions_other_region"] >= 1
