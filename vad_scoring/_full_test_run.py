"""Full-pipeline smoke test against one freedom wall (CAR-PUB-1, smallest).

Run this with `python _full_test_run.py` from inside vad_scoring/.
Writes progress to _full_test_run.log so external watchers can tail it.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

from vad_scoring.dotenv import autoload
from vad_scoring.io_utils import load_json, write_json
from vad_scoring.logging_setup import log_action

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "_full_test_run.log"


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
    CFG_PATH = ROOT / "configs" / f"{CFG_NAME}.json"

    template = load_json(ROOT / "configs" / "researcher_template.json")
    template["researcher_id"] = CFG_NAME
    template["assigned_universities"] = [UNIV]
    template["checkpoint_dir"] = f"checkpoints/{CFG_NAME}"
    template["output_dir"] = f"results/{CFG_NAME}"
    template["api_cache_path"] = f"api_cache/raw_responses_{CFG_NAME}.jsonl"
    write_json(CFG_PATH, template)
    _say(f"Wrote {CFG_PATH}")

    from vad_scoring import pipeline

    cfg = pipeline.load_config_bundle(ROOT, CFG_NAME)
    _say(f"prompt_sha256={cfg.prompt_sha256[:16]}...")
    _say(f"effective_rpm={cfg.researcher_cfg.get('effective_rpm')}")

    log_action(
        cfg.action_log_path, "PIPELINE_INIT", f"Full test run on {UNIV}",
        action=f"Started full VAD scoring on {UNIV} via temporary {CFG_NAME} config to validate end-to-end pipeline against real data.",
        configuration={
            "researcher_id": CFG_NAME,
            "assigned_universities": [UNIV],
            "model_id": cfg.vad_cfg["model_id"],
            "effective_rpm": cfg.researcher_cfg.get("effective_rpm", 20),
            "prompt_sha256": cfg.prompt_sha256,
        },
        inputs={
            "univ_code": UNIV,
            "expected_posts": 2287,
            "expected_batches": 458,
            "estimated_minutes": 23,
        },
    )

    started = time.time()
    _say(f"Starting full run on {UNIV}...")
    try:
        summary = pipeline.run_university(cfg, UNIV)
    except Exception as e:
        _say(f"FATAL: {e}")
        traceback.print_exc(file=sys.stderr)
        log_action(
            cfg.action_log_path, "PIPELINE_FAIL", f"Full test on {UNIV} FAILED",
            action=f"run_university({UNIV}) raised an unhandled exception",
            errors={"exception": str(e), "traceback": traceback.format_exc()},
        )
        return 1

    elapsed = time.time() - started
    summary["wall_clock_seconds"] = round(elapsed, 1)
    summary["wall_clock_minutes"] = round(elapsed / 60, 2)

    _say("=" * 60)
    _say("FINAL SUMMARY")
    _say("=" * 60)
    _say(json.dumps(summary, ensure_ascii=False, indent=2))

    log_action(
        cfg.action_log_path, "PIPELINE_DONE", f"Full test on {UNIV} complete",
        action=f"Pipeline completed for {UNIV} in {elapsed/60:.1f} minutes",
        outputs=summary,
        next_steps="Run validator (menu option 7) on the output JSONL; spot-check 50 random records for face validity; compare per-topic V/A/D distributions to expected priors before greenlighting full corpus.",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
