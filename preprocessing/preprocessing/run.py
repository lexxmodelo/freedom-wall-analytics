"""CLI entry-point: ``python -m preprocessing.run``."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .logging_setup import setup_logger
from .pipeline import PipelineConfig, run_pipeline


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESEARCH_ROOT = DEFAULT_PROJECT_ROOT.parent


def parse_phases(arg: str) -> set[int]:
    """Parse '1-10' or '4' or '2,5,8' or '1-3,7,9' into a set of ints."""
    out: set[int] = set()
    for chunk in arg.split(","):
        chunk = chunk.strip()
        if "-" in chunk:
            a, b = chunk.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        elif chunk:
            out.add(int(chunk))
    return out


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m preprocessing.run",
        description="Freedom Wall preprocessing pipeline (phases 01-10).",
    )
    p.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_RESEARCH_ROOT / "scraper_project" / "data",
        help="Directory containing input JSONL files (default: scraper_project/data).",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_PROJECT_ROOT / "output",
        help="Directory to write output JSON files (default: preprocessing/output).",
    )
    p.add_argument(
        "--schools-config",
        type=Path,
        default=DEFAULT_PROJECT_ROOT / "configs" / "schools.yaml",
    )
    p.add_argument(
        "--tagalog-names",
        type=Path,
        default=DEFAULT_PROJECT_ROOT / "configs" / "tagalog_given_names.txt",
    )
    p.add_argument(
        "--stopwords-dir",
        type=Path,
        default=DEFAULT_PROJECT_ROOT / "configs",
        help="Directory containing stopwords_<language>.txt files (auto-discovered).",
    )
    p.add_argument(
        "--phases",
        default="1-10",
        help="Phase selection: '1-10', '4', '2,5,8', etc. Default: all phases.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Per-file post limit (for development). Default: no limit.",
    )
    p.add_argument(
        "--near-dup-threshold",
        type=float,
        default=0.9,
    )
    p.add_argument(
        "--log-dir",
        type=Path,
        default=DEFAULT_PROJECT_ROOT / "logs",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    log = setup_logger("preprocessing", log_dir=args.log_dir)
    if args.verbose:
        log.setLevel(logging.DEBUG)
    cfg = PipelineConfig(
        input_dir=args.input,
        output_dir=args.output,
        schools_path=args.schools_config,
        tagalog_names_path=args.tagalog_names,
        stopwords_dir=args.stopwords_dir,
        limit=args.limit,
        phases=parse_phases(args.phases),
        near_dup_threshold=args.near_dup_threshold,
    )
    log.info("Running pipeline with config: %s", cfg)
    report = run_pipeline(cfg)
    log.info(
        "Done. kept=%d rejected=%d regions=%s",
        report.get("total_kept", 0),
        report.get("total_rejected", 0),
        report.get("by_region"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
