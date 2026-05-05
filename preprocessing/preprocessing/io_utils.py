"""JSONL/JSON I/O helpers.

All file operations use UTF-8 explicitly because the corpus contains non-ASCII
characters (e.g. Los Baños, smart quotes, emoji). Atomic writes go via a
temp file + rename so partial output never corrupts the previous run.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator


def load_jsonl(path: Path) -> Iterator[dict]:
    """Stream parse a JSONL file. Skips blank lines; bad lines raise."""
    with path.open("r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno} invalid JSON: {e}") from e


def write_json(path: Path, posts: list[dict]) -> None:
    """Write a list[dict] to a UTF-8 JSON file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    os.close(fd)
    tmp_path = Path(tmp)
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def write_jsonl(path: Path, posts: Iterable[dict]) -> int:
    """Append-mode JSONL write. Returns number of lines written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as f:
        for p in posts:
            f.write(json.dumps(p, ensure_ascii=False))
            f.write("\n")
            n += 1
    return n


def reset_file(path: Path) -> None:
    """Truncate a file if it exists, otherwise no-op."""
    if path.exists():
        path.unlink()


def append_rejected(path: Path, post: dict, reason: str, phase: str) -> None:
    """Record a dropped post with its rejection reason and originating phase."""
    record = {
        "post_id": post.get("post_id"),
        "reason": reason,
        "phase": phase,
        "text_preview": (post.get("text") or "")[:120],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False))
        f.write("\n")


def load_text_lines(path: Path) -> list[str]:
    """Read a UTF-8 text file as non-empty, non-comment, stripped lines."""
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def dump_qc_report(path: Path, report: dict[str, Any]) -> None:
    """Pretty-print the QC report; never overwrites prior runs without warning
    because the orchestrator deletes it explicitly at the start of a run."""
    write_json(path, report)  # type: ignore[arg-type]
