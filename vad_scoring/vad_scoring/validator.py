"""Validation layer for VAD parser output.

Two passes:

  1. reconcile_batch(parsed, expected_batch) — handles per-batch concerns
     (length mismatch, duplicate IDs, missing IDs). Returns (reconciled, missing,
     extras) so the pipeline knows what to re-queue.

  2. clamp_and_check(record) — single-record range and consistency checks
     (V/A/D ∈ [1,9], sarcasm-vs-valence consistency rule). Mutates the record
     in place to add `flags`. Returns the record.

Per the user's plan §6 error matrix:
  - Out-of-range V/A/D → CLAMP, flag `range_clamped`, do NOT retry
  - sarcasm=true AND V≥7 → flag `sarcasm_high_valence`, accept output (HITL later)
  - duplicate IDs → re-queue full batch (caller decides; we just report)
  - length mismatch → identify missing/extras, caller queues missing as singles
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .logging_setup import setup_logger

log = setup_logger(__name__)


@dataclass
class ReconcileResult:
    """Outcome of matching parsed records back to the expected batch."""
    reconciled: dict[str, dict] = field(default_factory=dict)  # post_id → coerced record
    missing_ids: list[str] = field(default_factory=list)        # in batch, not in response
    extra_ids: list[str] = field(default_factory=list)          # in response, not in batch
    duplicate_ids: list[str] = field(default_factory=list)      # appeared >1× in response


def reconcile_batch(parsed: list[dict], expected_batch: list[dict]) -> ReconcileResult:
    """Match parser output back to the expected batch by post_id.

    Returns ReconcileResult with:
      - `reconciled`: {post_id: parsed_record} for IDs present in BOTH (last
        occurrence wins on duplicates so the model's revised score takes effect)
      - `missing_ids`: expected post_ids not in the response (caller re-queues)
      - `extra_ids`: response post_ids not in the batch (caller drops + logs)
      - `duplicate_ids`: response post_ids that appeared more than once
    """
    expected_ids = {p["post_id"] for p in expected_batch}
    seen: dict[str, int] = {}
    reconciled: dict[str, dict] = {}
    extra_ids: list[str] = []
    duplicate_ids: list[str] = []

    for rec in parsed:
        pid = rec.get("id")
        if pid is None:
            continue
        seen[pid] = seen.get(pid, 0) + 1
        if seen[pid] > 1:
            if pid not in duplicate_ids:
                duplicate_ids.append(pid)
        if pid in expected_ids:
            reconciled[pid] = rec
        else:
            if pid not in extra_ids:
                extra_ids.append(pid)

    missing_ids = [p["post_id"] for p in expected_batch if p["post_id"] not in reconciled]
    return ReconcileResult(
        reconciled=reconciled,
        missing_ids=missing_ids,
        extra_ids=extra_ids,
        duplicate_ids=duplicate_ids,
    )


def clamp_and_check(
    record: dict,
    *,
    scale_min: int = 1,
    scale_max: int = 9,
) -> dict:
    """Clamp V/A/D to [scale_min, scale_max] and apply consistency rules.

    Mutates `record` to add a `flags: list[str]` and returns it.
    Range-clamp flags:
      - "range_clamped"        — at least one of V/A/D was out of range
      - "v_clamped" / "a_clamped" / "d_clamped" — per-dimension specifics
    Consistency flags:
      - "sarcasm_high_valence" — sarcasm=true AND V >= 7 (see §6 matrix)
      - "non_integer_score"    — model returned a float; rounded to nearest int
    """
    flags: list[str] = list(record.get("flags") or [])
    any_clamp = False

    for k in ("V", "A", "D"):
        v = record.get(k)
        if v is None:
            # parser would have raised; if we got here something is wrong upstream
            flags.append(f"{k.lower()}_missing")
            record[k] = scale_min
            any_clamp = True
            continue

        # Round floats first so range check is on integers.
        if isinstance(v, float) and not v.is_integer():
            record[k] = int(round(v))
            flags.append("non_integer_score")
            v = record[k]
        else:
            try:
                record[k] = int(v)
                v = record[k]
            except (TypeError, ValueError):
                # parser should have caught this; defensive fallback
                record[k] = scale_min
                flags.append(f"{k.lower()}_unparseable")
                any_clamp = True
                continue

        if v < scale_min:
            record[k] = scale_min
            flags.append(f"{k.lower()}_clamped")
            any_clamp = True
        elif v > scale_max:
            record[k] = scale_max
            flags.append(f"{k.lower()}_clamped")
            any_clamp = True

    if any_clamp:
        flags.insert(0, "range_clamped")

    # Consistency: sarcasm=true with surface-positive V is interesting (HITL bait)
    if record.get("sarcasm") is True and record.get("V", 0) >= 7:
        flags.append("sarcasm_high_valence")

    record["flags"] = flags
    return record


def is_pure_pass(record: dict) -> bool:
    """True when no flags fired — useful for stats dashboards."""
    return not record.get("flags")
