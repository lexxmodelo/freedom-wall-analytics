"""Per-(researcher, university) batch-level checkpointing.

Unlike topic_modeling.checkpoint (which only marks a university as complete or
not), VAD scoring needs FINE-GRAINED resume because a single university can
take 30+ minutes and crashes mid-run are realistic. State is written every
`checkpoint_frequency_requests` successful API calls (default: 100).

Schema (per plan §5):
  {
    "task": "vad_scoring",
    "researcher_id": "researcher_2",
    "univ_code": "CAR-PSEC-1",
    "total_batches": 773,
    "last_completed_batch": 154,
    "completed_post_ids_count": 770,
    "failed_post_ids": ["abc","xyz"],
    "successful_requests": 154,
    "failed_requests": 2,
    "out_of_range_clamps": 5,
    "sarcasm_flags": 18,
    "started_at": "...",
    "last_updated": "..."
  }

Resume rule: pipeline starts from batch index `last_completed_batch + 1`.
The completed_post_ids set is also persisted as a sidecar file
`<CODE>_completed_ids.txt` so resume is bullet-proof against partial batch
writes (we always trust the SET over the COUNTER).
"""
from __future__ import annotations

from pathlib import Path

from .io_utils import load_json, write_json
from .logging_setup import now_pht_iso, setup_logger

log = setup_logger(__name__)


def state_path(checkpoint_dir: Path, univ_code: str) -> Path:
    return checkpoint_dir / f"{univ_code}_state.json"


def completed_ids_path(checkpoint_dir: Path, univ_code: str) -> Path:
    return checkpoint_dir / f"{univ_code}_completed_ids.txt"


def load_state(checkpoint_dir: Path, univ_code: str) -> dict | None:
    p = state_path(checkpoint_dir, univ_code)
    if not p.exists():
        return None
    try:
        return load_json(p)
    except Exception as e:
        log.error("Corrupted checkpoint %s: %s", p, e)
        return None


def load_completed_ids(checkpoint_dir: Path, univ_code: str) -> set[str]:
    p = completed_ids_path(checkpoint_dir, univ_code)
    if not p.exists():
        return set()
    return {line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()}


def append_completed_ids(checkpoint_dir: Path, univ_code: str, post_ids: list[str]) -> None:
    p = completed_ids_path(checkpoint_dir, univ_code)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for pid in post_ids:
            f.write(pid + "\n")


def save_state(checkpoint_dir: Path, univ_code: str, state: dict) -> None:
    state = dict(state)
    state["last_updated"] = now_pht_iso()
    write_json(state_path(checkpoint_dir, univ_code), state)


def initial_state(researcher_id: str, univ_code: str, total_batches: int) -> dict:
    return {
        "task": "vad_scoring",
        "researcher_id": researcher_id,
        "univ_code": univ_code,
        "total_batches": total_batches,
        "last_completed_batch": -1,
        "completed_post_ids_count": 0,
        "failed_post_ids": [],
        "successful_requests": 0,
        "failed_requests": 0,
        "out_of_range_clamps": 0,
        "sarcasm_flags": 0,
        "pii_rejected_count": 0,
        "started_at": now_pht_iso(),
        "last_updated": now_pht_iso(),
        "complete": False,
    }


def is_complete(state: dict) -> bool:
    return bool(state.get("complete"))


def list_completed_universities(checkpoint_dir: Path) -> list[str]:
    if not checkpoint_dir.exists():
        return []
    out: list[str] = []
    for p in checkpoint_dir.glob("*_state.json"):
        try:
            data = load_json(p)
            if data.get("complete"):
                out.append(data.get("univ_code", p.stem.replace("_state", "")))
        except Exception:
            continue
    return out
