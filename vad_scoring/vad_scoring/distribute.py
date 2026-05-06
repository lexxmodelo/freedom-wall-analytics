"""Adaptive 1-5 researcher workload distribution.

Given the 10 universities and their batch counts, partition them across N
researchers so the maximum researcher load is minimized. Greedy bin-packing by
batch-count works well at this scale (10 universities, N=1..5) — we sort the
universities by batch count descending and assign each to the currently-lightest
researcher.

This is the "longest processing time" (LPT) heuristic, which is provably within
4/3 of optimal for makespan scheduling — more than good enough for our 10-item,
N≤5 case where the optimal split is usually obvious.

Universities with KNOWN counts come from the verified workload table in plan §1
(the topic_modeling outputs determine which posts exist; the actual batch count
per university is computed at runtime from len(topic_assignments)).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .batcher import load_topic_assignments
from .io_utils import load_yaml


# Hard-coded fallback counts from plan §1 (used only when topic_modeling outputs
# can't be read — e.g., for the `print_estimate` UI before any pipeline ran).
_FALLBACK_BATCHES = {
    "MM-PSEC-1": 747, "MM-PUB-1": 716, "MM-PNSEC-1": 793, "PROV-PUB-1": 791,
    "CAR-PNSEC-2": 783, "MIN-PUB-1": 800, "CAR-PUB-1": 458, "CAR-PUB-2": 759,
    "CAR-PNSEC-1": 799, "CAR-PSEC-1": 773,
}


@dataclass
class ResearcherSlice:
    researcher_index: int                       # 1..N
    universities: list[str] = field(default_factory=list)
    total_batches: int = 0


def get_active_universities(mapping_path: Path) -> list[str]:
    """Return the anon codes of all active+mapped universities, sorted alphabetically."""
    data = load_yaml(mapping_path)
    out: list[str] = []
    for fname, m in data.get("mappings", {}).items():
        if not m.get("active", True):
            continue
        code = m.get("code")
        if not code or str(code).upper() == "TBD":
            continue
        out.append(code)
    return sorted(out)


def count_batches_per_university(
    universities: Iterable[str],
    *,
    topic_outputs_dir: Path | None = None,
    batch_size: int = 5,
) -> dict[str, int]:
    """For each university, count batches = ceil(n_assignments / batch_size).

    Reads topic_modeling/outputs/<CODE>/topic_assignments.json when available;
    falls back to the hard-coded plan §1 numbers for any university whose
    assignments file is missing (lets the menu show estimates before
    topic_modeling has actually run).
    """
    out: dict[str, int] = {}
    for code in universities:
        n_batches = _FALLBACK_BATCHES.get(code, 0)
        if topic_outputs_dir is not None:
            p = topic_outputs_dir / code / "topic_assignments.json"
            if p.exists():
                try:
                    n = len(load_topic_assignments(p))
                    n_batches = (n + batch_size - 1) // batch_size
                except Exception:
                    pass  # fall back to plan number
        out[code] = n_batches
    return out


def balance_assignments(
    universities: Iterable[str],
    n_researchers: int,
    *,
    topic_outputs_dir: Path | None = None,
    batch_size: int = 5,
) -> list[ResearcherSlice]:
    """LPT greedy bin-pack of universities across n_researchers.

    Returns a list of ResearcherSlice with researcher_index 1..n_researchers,
    sorted by index. Each slice's `total_batches` is filled in.

    Raises ValueError if n_researchers not in 1..5 or no universities.
    """
    if not (1 <= n_researchers <= 5):
        raise ValueError(f"n_researchers must be 1-5, got {n_researchers}")
    counts = count_batches_per_university(
        universities, topic_outputs_dir=topic_outputs_dir, batch_size=batch_size,
    )
    if not counts:
        raise ValueError("no universities to distribute")

    # Sort universities by batch count descending (LPT)
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    slices = [ResearcherSlice(researcher_index=i + 1) for i in range(n_researchers)]
    for code, n in ordered:
        # Pick the slice with the least total_batches; tiebreak by index for determinism.
        target = min(slices, key=lambda s: (s.total_batches, s.researcher_index))
        target.universities.append(code)
        target.total_batches += n

    # Sort each slice's universities alphabetically for predictable display.
    for s in slices:
        s.universities.sort()
    return slices


def estimate_minutes(total_batches: int, effective_rpm: int) -> float:
    if effective_rpm <= 0:
        return float("inf")
    return total_batches / effective_rpm


def format_slice_table(slices: list[ResearcherSlice], effective_rpm: int = 20) -> str:
    """Pretty multi-line string for menu display."""
    lines = [
        f"{'Researcher':<11} | {'Universities':<60} | {'Batches':>7} | {'Time @ ' + str(effective_rpm) + ' RPM':>14}",
        "-" * 100,
    ]
    for s in slices:
        unis = ", ".join(s.universities)
        mins = estimate_minutes(s.total_batches, effective_rpm)
        lines.append(f"R{s.researcher_index:<10}| {unis:<60} | {s.total_batches:>7d} | {mins:>10.0f} min")
    total = sum(s.total_batches for s in slices)
    lines.append("-" * 100)
    lines.append(f"{'TOTAL':<11} | {'':<60} | {total:>7d} |")
    return "\n".join(lines)
