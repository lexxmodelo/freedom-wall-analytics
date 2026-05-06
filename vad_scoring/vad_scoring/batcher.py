"""Build per-university batches of (post_id, text, topic_label) ready for VAD scoring.

Joins three sources by post_id:
  1. preprocessing/output/{FW-NN}_cleaned.json — post text
  2. topic_modeling/outputs/{CODE}/topic_assignments.json — post_id → topic_id
  3. topic_modeling/outputs/{CODE}/topic_labels.json — topic_id → label

Outlier posts (topic_id == -1) get topic_label = vad_config.outlier_topic_label
(default "Unclassified") — the user decided in the planning phase to score them
rather than skip, to preserve dataset completeness for cross-institution analysis.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .io_utils import load_json, load_yaml
from .logging_setup import setup_logger

log = setup_logger(__name__)


def reverse_university_mapping(mapping_yaml: dict) -> dict[str, str]:
    """{anon_code: source_filename} from {source_filename: {code, ...}}."""
    out: dict[str, str] = {}
    for fname, m in mapping_yaml.get("mappings", {}).items():
        if not m.get("active", True):
            continue
        code = m.get("code")
        if not code or str(code).upper() == "TBD":
            continue
        out[code] = fname
    return out


def truncate_text(text: str, max_chars: int, suffix: str = " [truncated]") -> tuple[str, bool]:
    """Truncate text to max_chars, preserving the TAIL (most recent context).

    Most freedom-wall posts put the emotional core at the end (rant resolution,
    reaction emoji); keeping the tail rather than the head preserves more signal
    for VAD scoring on overlong posts.
    """
    if len(text) <= max_chars:
        return text, False
    return text[-max_chars:] + suffix, True


def load_topic_label_index(topic_labels_path: Path) -> dict[int, str]:
    """{topic_id: label} from topic_labels.json (list of dicts)."""
    items = load_json(topic_labels_path)
    return {int(t["topic_id"]): t.get("label", "Unlabeled") for t in items}


def load_post_text_index(cleaned_path: Path) -> dict[str, str]:
    """{post_id: text} from preprocessing/output/<FW>_cleaned.json (list of dicts)."""
    items = load_json(cleaned_path)
    out: dict[str, str] = {}
    for p in items:
        pid = p.get("post_id")
        if pid:
            out[pid] = p.get("text", "")
    return out


def load_topic_assignments(assignments_path: Path) -> list[dict]:
    """Returns list of {post_id, topic_id, probability?}."""
    return load_json(assignments_path)


def join_university(
    *,
    univ_code: str,
    cleaned_path: Path,
    assignments_path: Path,
    labels_path: Path,
    outlier_topic_label: str = "Unclassified",
    max_post_chars: int = 1500,
    truncation_suffix: str = " [truncated]",
) -> list[dict]:
    """Produce the per-post records ready to batch.

    Returns a list of dicts with shape:
        {post_id, univ_code, topic_id, topic_label, text, truncated: bool}
    Posts whose post_id is missing from preprocessing output are dropped with a
    warning (this should not happen if topic_modeling ran on the same files).
    """
    text_index = load_post_text_index(cleaned_path)
    label_index = load_topic_label_index(labels_path)
    assignments = load_topic_assignments(assignments_path)

    out: list[dict] = []
    missing_text = 0
    truncated_count = 0
    for a in assignments:
        pid = a["post_id"]
        if pid not in text_index:
            missing_text += 1
            continue
        topic_id = int(a.get("topic_id", -1))
        if topic_id == -1:
            label = outlier_topic_label
        else:
            label = label_index.get(topic_id, outlier_topic_label)
        text, truncated = truncate_text(
            text_index[pid], max_post_chars, truncation_suffix,
        )
        if truncated:
            truncated_count += 1
        out.append({
            "post_id": pid,
            "univ_code": univ_code,
            "topic_id": topic_id,
            "topic_label": label,
            "text": text,
            "truncated": truncated,
        })
    if missing_text:
        log.warning("[%s] %d post_ids in topic_assignments had no matching text in preprocessing output",
                    univ_code, missing_text)
    if truncated_count:
        log.info("[%s] truncated %d posts to %d chars (tail-preserving)",
                 univ_code, truncated_count, max_post_chars)
    return out


def chunk_into_batches(records: list[dict], batch_size: int = 5) -> Iterator[list[dict]]:
    """Yield successive batch_size-sized chunks. Last batch may be smaller."""
    for i in range(0, len(records), batch_size):
        yield records[i:i + batch_size]


def load_university_mapping(mapping_path: Path) -> dict[str, str]:
    """Convenience: load YAML and reverse to {code: filename}."""
    return reverse_university_mapping(load_yaml(mapping_path))
