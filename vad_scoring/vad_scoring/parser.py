"""Parse the model's JSON-array response into per-post records.

Recovery ladder (per plan §6 error matrix):
  1. json.loads on the full response
  2. extract first [...] block via regex, json.loads that
  3. attempt json_repair (lazy import — only if installed)
  4. raise ParseError so the caller can retry the whole batch

Returned records are dicts with shape:
  {"id": str, "V": int|float, "A": int|float, "D": int|float, "sarcasm": bool}

The parser does NOT enforce range — that is the validator's job.
The parser DOES coerce types (string "5" → int 5, "true" → True).
"""
from __future__ import annotations

import json
import re
from typing import Any


class ParseError(Exception):
    """Raised when no JSON array of dicts can be extracted from the response."""


_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)


def _coerce_record(rec: Any) -> dict:
    """Best-effort coerce a single record dict.

    - keeps string id; rejects record without id
    - V/A/D: int(str) accepted; float accepted (validator clamps)
    - sarcasm: bool accepted; string "true"/"false" coerced
    """
    if not isinstance(rec, dict):
        raise ParseError(f"record is not a dict: {type(rec).__name__}")
    out: dict[str, Any] = {}
    pid = rec.get("id") or rec.get("post_id")
    if not pid:
        raise ParseError(f"record missing id: {rec!r}")
    out["id"] = str(pid)
    for k in ("V", "A", "D"):
        v = rec.get(k)
        if v is None:
            raise ParseError(f"record {pid} missing {k}")
        if isinstance(v, bool):
            raise ParseError(f"record {pid} {k} is bool, expected number")
        try:
            out[k] = int(v)
        except (TypeError, ValueError):
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                raise ParseError(f"record {pid} {k}={v!r} not numeric")
    s = rec.get("sarcasm", False)
    if isinstance(s, str):
        s = s.strip().lower() in ("true", "1", "yes", "y")
    out["sarcasm"] = bool(s)
    return out


def _try_json_repair(text: str) -> Any:
    """Lazy json_repair fallback. Returns None if the library is not installed."""
    try:
        from json_repair import repair_json  # type: ignore
    except ImportError:
        return None
    try:
        repaired = repair_json(text, return_objects=True)
    except Exception:
        return None
    return repaired


def parse_response(text: str) -> list[dict]:
    """Parse the model response into a list of coerced records.

    Raises ParseError if no valid array can be recovered.
    """
    if not text or not text.strip():
        raise ParseError("empty response")

    # Strategy 1: direct json.loads
    candidates: list[Any] = []
    try:
        parsed = json.loads(text)
        candidates.append(parsed)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract first [...] block
    if not candidates:
        m = _ARRAY_RE.search(text)
        if m:
            try:
                candidates.append(json.loads(m.group(0)))
            except json.JSONDecodeError:
                pass

    # Strategy 3: json_repair
    if not candidates:
        repaired = _try_json_repair(text)
        if repaired is not None:
            candidates.append(repaired)

    # Try each candidate; first one that produces records wins.
    last_exc: Exception | None = None
    for c in candidates:
        if isinstance(c, dict):
            # model returned a single object instead of a list
            try:
                return [_coerce_record(c)]
            except ParseError as e:
                last_exc = e
                continue
        if isinstance(c, list):
            try:
                return [_coerce_record(r) for r in c]
            except ParseError as e:
                last_exc = e
                continue
    raise ParseError(f"unable to parse response: {last_exc or 'no JSON array found'}")
