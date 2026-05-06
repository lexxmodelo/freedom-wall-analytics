"""Tiny .env file loader. No external dep; sufficient for KEY=VALUE files.

Provenance: copied verbatim from topic_modeling/topic_modeling/dotenv.py to keep
the vad_scoring package self-contained (no sys.path hacks, no cross-package imports).

Loads `.env` from the vad_scoring/ root and from the project root (parent).
Variables already set in the real environment are NOT overwritten.

Lines:
  - blank or `#`-prefixed are skipped
  - `KEY=VALUE` (no spaces around `=`)
  - Surrounding quotes (single or double) on VALUE are stripped
  - `export KEY=VALUE` (bash-style) prefix is supported
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$", re.IGNORECASE)


def load_dotenv_files(*candidates: Path, override: bool = False) -> dict[str, str]:
    """Load each existing .env file in `candidates` order. Later files override
    earlier ones (within the .env layer); the real os.environ is only modified
    if the variable is currently unset (or override=True)."""
    out: dict[str, str] = {}
    for path in candidates:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = _LINE_RE.match(line)
            if not m:
                continue
            key, val = m.group(1), m.group(2)
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            out[key] = val
    for k, v in out.items():
        if override or k not in os.environ:
            os.environ[k] = v
    return out


def autoload(root: Path) -> dict[str, str]:
    """Standard convenience: load vad_scoring/.env and project_root/.env."""
    return load_dotenv_files(root / ".env", root.parent / ".env")
