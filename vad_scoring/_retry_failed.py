"""Recover failed_post_ids for CAR-PUB-1 (validates the retry path).

Logs to _retry_failed.log so external watchers can tail it.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

from vad_scoring.dotenv import autoload

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "_retry_failed.log"


def _say(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> int:
    LOG.write_text("", encoding="utf-8")
    autoload(ROOT)

    UNIV = "CAR-PUB-1"
    CFG_NAME = "researcher_test"
    from vad_scoring import pipeline

    cfg = pipeline.load_config_bundle(ROOT, CFG_NAME)
    _say(f"Starting retry for {UNIV}...")
    started = time.time()
    try:
        summary = pipeline.retry_failed_posts(cfg, UNIV)
    except Exception as e:
        _say(f"FATAL: {e}")
        traceback.print_exc(file=sys.stderr)
        return 1

    summary["wall_clock_seconds"] = round(time.time() - started, 1)
    _say("=" * 60)
    _say("RETRY SUMMARY")
    _say("=" * 60)
    _say(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
