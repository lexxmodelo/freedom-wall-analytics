"""Centralized logging for the vad_scoring pipeline.

Provenance: adapted from topic_modeling/topic_modeling/logging_setup.py.
Logs go to stderr and an optional per-run file; `log_action()` appends Markdown
entries to action_log.md so the audit trail and console logs stay in sync.
"""
from __future__ import annotations

import logging
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

PHT = timezone(timedelta(hours=8), name="Asia/Manila")

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s"


def setup_logger(name: str, log_dir: Path | None = None) -> logging.Logger:
    """Create or return a configured logger. Idempotent by name."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(_FORMAT)

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(PHT).strftime("%Y%m%d_%H%M%S")
        fh = logging.FileHandler(log_dir / f"vad_scoring_{stamp}.log", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.propagate = False
    return logger


def now_pht_iso() -> str:
    """Current PHT timestamp in ISO 8601."""
    return datetime.now(PHT).strftime("%Y-%m-%dT%H:%M:%S%z")


def log_action(
    action_log_path: Path,
    action_type: str,
    title: str,
    *,
    action: str = "",
    configuration: Any = None,
    inputs: Any = None,
    outputs: Any = None,
    errors: Any = None,
    decisions: str = "",
    next_steps: str = "",
) -> None:
    """Append an ACTION-NNN entry to action_log.md.

    Auto-increments the action number by reading the existing file. Format mirrors
    topic_modeling/action_log.md.
    """
    n = _next_action_number(action_log_path)
    date = datetime.now(PHT).strftime("%Y-%m-%d")
    time = datetime.now(PHT).strftime("%H:%M:%S")
    parts = [
        f"## ACTION-{n:03d} — {date} — {title}",
        "",
        f"_Logged at {time} PHT — type: `{action_type}`_",
        "",
    ]
    if action:
        parts += [f"- **Action:** {action}"]
    if configuration is not None:
        parts += [f"- **Configuration:** {_render_block(configuration)}"]
    if inputs is not None:
        parts += [f"- **Input:** {_render_block(inputs)}"]
    if outputs is not None:
        parts += [f"- **Output:** {_render_block(outputs)}"]
    if errors is not None:
        parts += [f"- **Errors:** {_render_block(errors)}"]
    if decisions:
        parts += [f"- **Decisions:** {decisions}"]
    if next_steps:
        parts += [f"- **Next Steps:** {next_steps}"]
    parts += ["", "---", ""]

    action_log_path.parent.mkdir(parents=True, exist_ok=True)
    with action_log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(parts))


_ACTION_RE = re.compile(r"^## ACTION-(\d+)", re.MULTILINE)


def _next_action_number(path: Path) -> int:
    if not path.exists():
        return 1
    text = path.read_text(encoding="utf-8")
    nums = [int(m.group(1)) for m in _ACTION_RE.finditer(text)]
    return (max(nums) + 1) if nums else 1


def _render_block(value: Any) -> str:
    """Render a value as Markdown — short scalars inline, dicts/lists as fenced JSON."""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return repr(value)
    import json
    return "\n```json\n" + json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n```"
