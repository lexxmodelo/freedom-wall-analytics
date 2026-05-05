"""Checkpoint round-trip tests."""
from __future__ import annotations

from topic_modeling.checkpoint import (checkpoint_exists, list_completed,
                                       load_checkpoint, write_checkpoint)


def test_checkpoint_round_trip(tmp_path):
    cp_dir = tmp_path / "checkpoints" / "researcher_1"
    code = "CAR-PSEC-1"

    assert not checkpoint_exists(cp_dir, code)
    assert load_checkpoint(cp_dir, code) is None
    assert list_completed(cp_dir) == []

    write_checkpoint(
        cp_dir, code,
        researcher_id="researcher_1",
        n_posts=3864,
        n_topics=22,
        outlier_rate=0.42,
        bakeoff_winner="paraphrase-multilingual-MiniLM-L12-v2",
    )

    assert checkpoint_exists(cp_dir, code)
    data = load_checkpoint(cp_dir, code)
    assert data["complete"] is True
    assert data["university_code"] == code
    assert data["n_posts"] == 3864
    assert data["embedding_model"] == "paraphrase-multilingual-MiniLM-L12-v2"
    assert "completed_at" in data

    assert list_completed(cp_dir) == [code]


def test_checkpoint_with_extras(tmp_path):
    cp_dir = tmp_path / "cp"
    write_checkpoint(
        cp_dir, "MM-PUB-1",
        researcher_id="r2", n_posts=10, n_topics=2,
        outlier_rate=0.1,
        extras={"hdbscan_params": {"min_cluster_size": 50, "min_samples": 10},
                "needs_review": False},
    )
    data = load_checkpoint(cp_dir, "MM-PUB-1")
    assert data["hdbscan_params"]["min_cluster_size"] == 50
    assert data["needs_review"] is False


def test_checkpoint_corrupt_file_treated_as_missing(tmp_path):
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir(parents=True)
    (cp_dir / "FOO_state.json").write_text("not json", encoding="utf-8")
    assert checkpoint_exists(cp_dir, "FOO") is False
