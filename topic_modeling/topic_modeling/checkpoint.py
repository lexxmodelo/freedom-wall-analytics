"""Resume support for the topic_modeling pipeline.

A checkpoint marks a (researcher_id, university_code) pair as fully complete:
clustering trained, labels produced, all output JSONs written. On restart the
pipeline skips any university with an existing checkpoint.

Partial progress within a single university is NOT checkpointed — BERTopic
clustering is fast enough (<10 min/uni) that re-running from scratch is cheaper
than the bookkeeping of intermediate state.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .io_utils import load_json, write_json
from .logging_setup import now_pht_iso


def checkpoint_path(checkpoint_dir: Path, univ_code: str) -> Path:
    return checkpoint_dir / f"{univ_code}_state.json"


def checkpoint_exists(checkpoint_dir: Path, univ_code: str) -> bool:
    p = checkpoint_path(checkpoint_dir, univ_code)
    if not p.exists():
        return False
    try:
        data = load_json(p)
        return bool(data.get("complete", False))
    except Exception:
        return False


def write_checkpoint(
    checkpoint_dir: Path,
    univ_code: str,
    *,
    researcher_id: str,
    n_posts: int,
    n_topics: int,
    outlier_rate: float,
    bakeoff_winner: str | None = None,
    extras: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "complete": True,
        "researcher_id": researcher_id,
        "university_code": univ_code,
        "completed_at": now_pht_iso(),
        "n_posts": n_posts,
        "n_topics": n_topics,
        "outlier_rate": outlier_rate,
        "embedding_model": bakeoff_winner,
    }
    if extras:
        payload.update(extras)
    write_json(checkpoint_path(checkpoint_dir, univ_code), payload)


def load_checkpoint(checkpoint_dir: Path, univ_code: str) -> dict | None:
    p = checkpoint_path(checkpoint_dir, univ_code)
    if not p.exists():
        return None
    return load_json(p)


def list_completed(checkpoint_dir: Path) -> list[str]:
    if not checkpoint_dir.exists():
        return []
    out: list[str] = []
    for p in checkpoint_dir.glob("*_state.json"):
        try:
            data = load_json(p)
            if data.get("complete"):
                out.append(data.get("university_code", p.stem.replace("_state", "")))
        except Exception:
            continue
    return out
