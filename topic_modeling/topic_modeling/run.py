"""CLI entry point: `python -m topic_modeling.run --researcher researcher_1`.

Flags:
  --researcher ID         Required. Selects configs/<ID>.json.
  --root PATH             Defaults to the topic_modeling/ directory containing this file.
  --input-dir PATH        Override input directory (default: ../preprocessing/output).
  --bakeoff-only          Run only the embedding bake-off; skip per-university training.
  --skip-bakeoff          Use the embedding_model_id already in bertopic_config.json.
  --verbose               Set INFO -> DEBUG console logging.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .logging_setup import setup_logger
from .pipeline import load_config_bundle, run


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="topic_modeling", description=__doc__)
    p.add_argument("--researcher", required=True,
                   help="Researcher ID (matches configs/<id>.json filename without extension)")
    p.add_argument("--root", default=None,
                   help="topic_modeling/ root path (default: directory containing this script's parent)")
    p.add_argument("--input-dir", default=None,
                   help="Override input directory (default: ../preprocessing/output)")
    p.add_argument("--bakeoff-only", action="store_true")
    p.add_argument("--skip-bakeoff", action="store_true")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)

    if args.bakeoff_only and args.skip_bakeoff:
        print("ERROR: --bakeoff-only and --skip-bakeoff are mutually exclusive", file=sys.stderr)
        return 2

    # The package lives at <root>/topic_modeling/; the project root is the parent.
    here = Path(__file__).resolve().parent
    root = Path(args.root).resolve() if args.root else here.parent

    log = setup_logger("topic_modeling.run", log_dir=root / "gpu_logs")
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    log.info("Project root: %s", root)

    cfg = load_config_bundle(
        root, args.researcher,
        bakeoff_only=args.bakeoff_only,
        skip_bakeoff=args.skip_bakeoff,
    )
    if args.input_dir:
        cfg.input_dir = Path(args.input_dir).resolve()
    log.info("Researcher=%s, input_dir=%s, assigned=%s",
             args.researcher, cfg.input_dir, cfg.researcher_cfg.get("assigned_files"))

    summary = run(cfg)
    log.info("Done. Summary: %s", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
