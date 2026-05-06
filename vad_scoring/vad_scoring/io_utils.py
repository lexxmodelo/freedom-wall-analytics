"""JSON / JSONL / YAML / text-file I/O helpers.

Provenance: copied verbatim from topic_modeling/topic_modeling/io_utils.py to keep
the vad_scoring package self-contained. All file ops are UTF-8 explicit because
the corpus contains non-ASCII characters (Filipino, Cebuano, emoji).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator


def load_json(path: Path) -> Any:
    """Read a UTF-8 JSON file and return the parsed object."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    """Atomic JSON write via temp-file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    os.close(fd)
    tmp_path = Path(tmp)
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


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


def append_jsonl(path: Path, records: Iterable[dict]) -> int:
    """Append-mode JSONL write. Returns number of lines written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False))
            f.write("\n")
            n += 1
    return n


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


def load_yaml(path: Path) -> Any:
    """Read a UTF-8 YAML file. Importing pyyaml lazily so callers without the
    dep can still import the rest of this module."""
    import yaml
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def sha256_text(text: str) -> str:
    """Return the hex sha256 digest of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """Hex sha256 of a file's bytes."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
