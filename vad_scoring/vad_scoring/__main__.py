"""Interactive launcher: `python -m vad_scoring`.

Nine-option menu (per plan §9). UI helpers `_input`, `_yesno`, `_menu`,
`_multiselect`, `pick_researcher`, `ensure_dotenv` mirror the topic_modeling
launcher to keep the operator experience consistent across phases.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

from . import distribute, merge, pipeline, pii_check, prompt as prompt_mod, validator as vad_validator
from .checkpoint import (
    list_completed_universities, load_state,
)
from .dotenv import autoload as autoload_dotenv
from .io_utils import load_json, write_json
from .logging_setup import log_action
from .parser import ParseError, parse_response


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIGS = ROOT / "configs"


# ---------- low-level UI helpers ----------

def _input(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or (default or "")


def _yesno(prompt: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    val = input(f"{prompt} ({d}): ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def _menu(title: str, options: list[tuple[str, str]]) -> str:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)
    for k, lbl in options:
        print(f"  {k}. {lbl}")
    while True:
        choice = input("Choose: ").strip()
        if any(choice == k for k, _ in options):
            return choice
        print("Invalid choice. Try again.")


def _int_in_range(prompt: str, lo: int, hi: int, default: int | None = None) -> int:
    while True:
        raw = _input(prompt, str(default) if default is not None else None)
        if not raw:
            continue
        try:
            v = int(raw)
        except ValueError:
            print(f"Not an integer. Enter {lo}-{hi}.")
            continue
        if lo <= v <= hi:
            return v
        print(f"Out of range. Enter {lo}-{hi}.")


# Files in configs/ that are NOT researcher configs (locked settings, templates, schemas).
_NON_RESEARCHER_CONFIGS = {
    "vad_config.json",
    "researcher_template.json",
    "vad_output.schema.json",
    "few_shot_examples.json",
}


def list_researcher_configs() -> list[str]:
    """Every *.json in configs/ that isn't a locked-settings file or template."""
    return sorted(
        p.stem for p in CONFIGS.glob("*.json")
        if p.name not in _NON_RESEARCHER_CONFIGS
    )


def pick_researcher(prompt: str = "Choose researcher:") -> str | None:
    rids = list_researcher_configs()
    if not rids:
        print("No researcher configs found. Run option 1 to create one.")
        return None
    print()
    print(prompt)
    for i, rid in enumerate(rids, start=1):
        print(f"  {i:2d}. {rid}")
    raw = input("Choose: ").strip()
    if not raw.isdigit():
        return None
    idx = int(raw)
    if 1 <= idx <= len(rids):
        return rids[idx - 1]
    return None


# ---------- .env bootstrap ----------

def ensure_dotenv() -> None:
    autoload_dotenv(ROOT)
    if os.environ.get("NVIDIA_NIM_API_KEY"):
        return

    print()
    print("No NVIDIA_NIM_API_KEY found in environment or .env.")
    print("Get a free key at https://build.nvidia.com (sign up, generate API key).")
    if not _yesno("Paste your API key now?", default=True):
        return
    key = input("Paste key (starts with nvapi-...): ").strip()
    if not key:
        print("No key entered. Continuing without one.")
        return
    env_path = ROOT / ".env"
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    if "NVIDIA_NIM_API_KEY" in existing:
        new_lines = []
        for line in existing.splitlines():
            if line.lstrip().startswith("NVIDIA_NIM_API_KEY"):
                new_lines.append(f"NVIDIA_NIM_API_KEY={key}")
            else:
                new_lines.append(line)
        content = "\n".join(new_lines) + "\n"
    else:
        content = (existing + ("\n" if existing and not existing.endswith("\n") else "")
                   + f"NVIDIA_NIM_API_KEY={key}\n")
    env_path.write_text(content, encoding="utf-8")
    os.environ["NVIDIA_NIM_API_KEY"] = key
    print(f"Saved to {env_path}.")


# ---------- helpers for actions ----------

def _load_vad_cfg() -> dict:
    return load_json(CONFIGS / "vad_config.json")


def _resolve_universities() -> list[str]:
    vad_cfg = _load_vad_cfg()
    mapping_path = (ROOT / vad_cfg["university_mapping_path"]).resolve()
    return distribute.get_active_universities(mapping_path)


def _topic_outputs_dir() -> Path:
    return (ROOT / _load_vad_cfg()["topic_modeling_outputs_dir"]).resolve()


# ---------- actions ----------

def action_setup_researcher() -> None:
    print()
    print("--- Set up researcher config ---")
    universities = _resolve_universities()
    if len(universities) == 0:
        print("No active universities in mapping. Aborting.")
        return

    print(f"Detected {len(universities)} active universities: {', '.join(universities)}")
    n = _int_in_range("How many researchers total? (1-5)", 1, 5, default=1)

    slices = distribute.balance_assignments(
        universities, n, topic_outputs_dir=_topic_outputs_dir(),
    )
    print()
    print("Proposed distribution:")
    print(distribute.format_slice_table(slices, effective_rpm=20))
    print()

    me = _int_in_range(f"Which researcher are you? (1-{n})", 1, n)
    my_slice = next(s for s in slices if s.researcher_index == me)

    rid = _input("Save config under researcher id", default=f"researcher_{me}")
    cfg_path = CONFIGS / f"{rid}.json"
    if cfg_path.exists():
        if not _yesno(f"{cfg_path.name} exists. Overwrite?", default=False):
            print("Cancelled.")
            return

    template = load_json(CONFIGS / "researcher_template.json")
    template["researcher_id"] = rid
    template["assigned_universities"] = my_slice.universities
    template["checkpoint_dir"] = f"checkpoints/{rid}"
    template["output_dir"] = f"results/{rid}"
    template["api_cache_path"] = f"api_cache/raw_responses_{rid}.jsonl"
    write_json(cfg_path, template)
    print(f"Wrote {cfg_path}")
    print(f"Assigned: {my_slice.universities} ({my_slice.total_batches} batches)")

    log_action(
        ROOT / "action_log.md", "SETUP", f"Researcher {rid} configured",
        action=f"Researcher {rid} initialized for {n}-way split",
        configuration={
            "researcher_id": rid,
            "n_researchers_total": n,
            "this_researcher_index": me,
            "assigned_universities": my_slice.universities,
            "total_batches": my_slice.total_batches,
            "effective_rpm": template.get("effective_rpm", 20),
        },
    )


def action_score_test_post() -> None:
    rid = pick_researcher("Use which researcher's API key?")
    if rid is None:
        return
    cfg = pipeline.load_config_bundle(ROOT, rid)

    print()
    print("--- Score single test post ---")
    pid = _input("post_id (any string)", default="test_post_1")
    text = _input("post text")
    if not text:
        print("Empty text; cancelled.")
        return
    topic = _input("topic label", default="Unclassified")

    expected = [{
        "post_id": pid, "univ_code": "CAR-PSEC-1",
        "topic_id": -1, "topic_label": topic, "text": text, "truncated": False,
    }]
    api_writer = pipeline._make_api_cache_writer(cfg.api_cache_path)
    client = pipeline._make_client(cfg, api_cache_writer=api_writer)
    try:
        records, missing, errs = pipeline.score_one_batch(
            client=client, batch=expected, few_shot=cfg.few_shot_examples,
            scale_min=int(cfg.vad_cfg.get("scale_min", 1)),
            scale_max=int(cfg.vad_cfg.get("scale_max", 9)),
        )
    finally:
        client.close()

    print()
    if records:
        for r in records:
            r["researcher_id"] = cfg.researcher_id
            print(json.dumps(r, ensure_ascii=False, indent=2))
    if missing:
        print(f"Missing IDs: {missing}")
    if errs:
        print(f"Errors: {errs}")


def action_score_test_batch() -> None:
    rid = pick_researcher("Use which researcher's API key?")
    if rid is None:
        return
    cfg = pipeline.load_config_bundle(ROOT, rid)

    print()
    if not cfg.assigned_universities:
        print("No assigned universities for this researcher. Run option 1 first.")
        return
    code = cfg.assigned_universities[0]
    print(f"Pulling first 5 posts from {code}...")
    fname = pipeline._resolve_filename(cfg, code)
    cleaned_path = cfg.preprocessing_outputs_dir / fname
    assignments_path = cfg.topic_outputs_dir / code / "topic_assignments.json"
    labels_path = cfg.topic_outputs_dir / code / "topic_labels.json"
    from . import batcher
    records = batcher.join_university(
        univ_code=code, cleaned_path=cleaned_path,
        assignments_path=assignments_path, labels_path=labels_path,
        outlier_topic_label=cfg.vad_cfg.get("outlier_topic_label", "Unclassified"),
        max_post_chars=int(cfg.vad_cfg.get("max_post_chars", 1500)),
    )[:5]
    if not records:
        print("No posts to score.")
        return

    api_writer = pipeline._make_api_cache_writer(cfg.api_cache_path)
    client = pipeline._make_client(cfg, api_cache_writer=api_writer)
    try:
        out, missing, errs = pipeline.score_one_batch(
            client=client, batch=records, few_shot=cfg.few_shot_examples,
            scale_min=int(cfg.vad_cfg.get("scale_min", 1)),
            scale_max=int(cfg.vad_cfg.get("scale_max", 9)),
        )
    finally:
        client.close()

    print()
    for r in out:
        r["researcher_id"] = cfg.researcher_id
        print(json.dumps(r, ensure_ascii=False))
    if missing:
        print(f"Missing IDs: {missing}")
    if errs:
        print(f"Errors: {errs}")


def action_run_full() -> None:
    rid = pick_researcher("Run full pipeline as which researcher?")
    if rid is None:
        return
    cfg = pipeline.load_config_bundle(ROOT, rid)
    print()
    print(f"Researcher {rid} will score: {cfg.assigned_universities}")
    print("Performing 1-batch dry-run first to verify connectivity + parsing...")
    if not _yesno("Continue with dry-run?", default=True):
        return
    if cfg.assigned_universities:
        first = cfg.assigned_universities[0]
        try:
            pipeline.run_university(cfg, first, dry_run_one_batch=True)
        except Exception as e:
            print(f"Dry-run failed: {e}")
            traceback.print_exc()
            return
    print("Dry-run complete.")
    if not _yesno("Proceed to FULL pipeline (this may take hours)?", default=False):
        print("Cancelled. State for the dry-run batch is preserved; option 5 will resume from there.")
        return

    log_action(
        ROOT / "action_log.md", "PIPELINE_INIT",
        f"Researcher {rid} starting full VAD scoring",
        action=f"Researcher {rid} began full VAD scoring",
        configuration={
            "researcher_id": rid,
            "assigned_universities": cfg.assigned_universities,
            "model_id": cfg.vad_cfg["model_id"],
            "temperature": cfg.vad_cfg["temperature"],
            "batch_size": cfg.vad_cfg["batch_size"],
            "effective_rpm": cfg.researcher_cfg.get("effective_rpm", 20),
            "prompt_sha256": cfg.prompt_sha256,
        },
    )

    summaries = pipeline.run_all(cfg)
    print()
    print("--- Summaries ---")
    for s in summaries:
        print(json.dumps(s, ensure_ascii=False))


def action_resume() -> None:
    rid = pick_researcher("Resume which researcher?")
    if rid is None:
        return
    cfg = pipeline.load_config_bundle(ROOT, rid)

    # Two distinct cases:
    #   (a) Universities not yet complete → resume their batch loop
    #   (b) Universities complete but with non-empty failed_post_ids → retry those posts
    pending: list[str] = []
    needs_retry: list[tuple[str, int]] = []
    for code in cfg.assigned_universities:
        st = load_state(cfg.checkpoint_dir, code)
        if st is None or not st.get("complete"):
            pending.append(code)
        else:
            n_failed = len(st.get("failed_post_ids", []))
            if n_failed > 0:
                needs_retry.append((code, n_failed))

    if not pending and not needs_retry:
        print("Nothing to resume — all assigned universities are complete and have no failed posts.")
        return

    if pending:
        print(f"Will RESUME (incomplete universities): {pending}")
    if needs_retry:
        retry_lines = [f"{code} ({n} failed posts)" for code, n in needs_retry]
        print(f"Will RETRY failed posts in: {', '.join(retry_lines)}")
    if not _yesno("Continue?", default=True):
        return

    if pending:
        summaries = pipeline.run_all(cfg)
        for s in summaries:
            print(json.dumps(s, ensure_ascii=False))
    for code, _n in needs_retry:
        s = pipeline.retry_failed_posts(cfg, code)
        print(json.dumps(s, ensure_ascii=False))


def action_show_progress() -> None:
    print()
    print("--- Progress ---")
    rids = list_researcher_configs()
    if not rids:
        print("No researcher configs.")
        return
    for rid in rids:
        rcfg = load_json(CONFIGS / f"{rid}.json")
        cp_dir = ROOT / rcfg["checkpoint_dir"]
        print()
        print(f"# {rid} (assigned: {rcfg.get('assigned_universities', [])})")
        if not cp_dir.exists():
            print("  (no checkpoints yet)")
            continue
        for code in rcfg.get("assigned_universities", []):
            st = load_state(cp_dir, code)
            if st is None:
                print(f"  [pending] {code}")
                continue
            done = st.get("last_completed_batch", -1) + 1
            total = st.get("total_batches", 0)
            mark = "[DONE]" if st.get("complete") else "[in-progress]"
            print(f"  {mark} {code}: {done}/{total} batches | "
                  f"clamps={st.get('out_of_range_clamps', 0)} | "
                  f"sarcasm={st.get('sarcasm_flags', 0)} | "
                  f"failed={st.get('failed_requests', 0)}")


def action_validate_outputs() -> None:
    rid = pick_researcher("Validate which researcher's outputs? (or pick __all__)")
    if rid is None:
        if not _yesno("No selection. Validate ALL researchers?", default=True):
            return
        targets = list_researcher_configs()
    else:
        targets = [rid]

    schema_path = CONFIGS / "vad_output.schema.json"
    schema = load_json(schema_path)
    required = set(schema.get("required", []))
    scale_min = schema["properties"]["V"]["minimum"]
    scale_max = schema["properties"]["V"]["maximum"]

    failures: list[dict] = []
    total = 0
    for tgt in targets:
        rcfg = load_json(CONFIGS / f"{tgt}.json")
        out_dir = ROOT / rcfg["output_dir"]
        for jsonl_file in sorted(out_dir.glob("*_vad_scores.jsonl")):
            with jsonl_file.open("r", encoding="utf-8") as f:
                for lineno, raw in enumerate(f, start=1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    total += 1
                    try:
                        rec = json.loads(raw)
                    except json.JSONDecodeError as e:
                        failures.append({"file": str(jsonl_file), "line": lineno, "issue": f"json: {e}"})
                        continue
                    missing = required - set(rec.keys())
                    if missing:
                        failures.append({"file": str(jsonl_file), "line": lineno,
                                         "post_id": rec.get("post_id"),
                                         "issue": f"missing fields: {sorted(missing)}"})
                        continue
                    for k in ("V", "A", "D"):
                        v = rec.get(k)
                        if not isinstance(v, int) or v < scale_min or v > scale_max:
                            failures.append({"file": str(jsonl_file), "line": lineno,
                                             "post_id": rec.get("post_id"),
                                             "issue": f"{k}={v} out of [{scale_min},{scale_max}]"})
    report = {
        "researchers_validated": targets,
        "records_scanned": total,
        "failures": failures,
        "pass_rate": round(100.0 * (total - len(failures)) / total, 3) if total else 0.0,
    }
    out_path = ROOT / "validation" / "schema_validation_report.json"
    write_json(out_path, report)
    print(f"Scanned {total} records | {len(failures)} failures | report: {out_path}")


def action_view_few_shot() -> None:
    path = CONFIGS / "few_shot_examples.json"
    data = load_json(path)
    print()
    print(f"--- Few-shot examples ({path.name}) ---")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print()
    print("Edit the file directly with your editor of choice.")
    print("Note: editing few_shot examples invalidates prompt_sha256 in vad_config.json.")
    print("Recommended: only edit BEFORE any pipeline run, not mid-run.")
    if _yesno("Recompute prompt_sha256 now (after you've saved your edits)?", default=False):
        new_sha = prompt_mod.compute_prompt_sha256(load_json(path)["examples"])
        vad = load_json(CONFIGS / "vad_config.json")
        old_sha = vad.get("prompt_sha256")
        vad["prompt_sha256"] = new_sha
        write_json(CONFIGS / "vad_config.json", vad)
        print(f"prompt_sha256: {old_sha} → {new_sha}")


def action_merge() -> None:
    print()
    print("--- Merge cross-researcher results ---")
    print("This action is intended for the LEAD researcher only.")
    if not _yesno("Are you the lead?", default=False):
        return
    summary = merge.merge(
        results_root=ROOT / "results",
        checkpoint_root=ROOT / "checkpoints",
        output_root=ROOT / "merged_outputs",
        force=False,
    ) if _safe_check_complete() else None
    if summary is None:
        # We'll re-call with force=True after asking
        if _yesno("Some researchers are not complete. Force merge anyway?", default=False):
            summary = merge.merge(
                results_root=ROOT / "results",
                checkpoint_root=ROOT / "checkpoints",
                output_root=ROOT / "merged_outputs",
                force=True,
            )
    if summary is not None:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        log_action(
            ROOT / "action_log.md", "MERGE", "Cross-researcher merge",
            action="Lead merged all researcher results into merged_outputs/",
            outputs=summary,
        )


def _safe_check_complete() -> bool:
    done, incomplete = merge.all_complete(ROOT / "checkpoints")
    if not done:
        print("Incomplete:")
        for line in incomplete:
            print(f"  - {line}")
    return done


# ---------- main loop ----------

MENU = [
    ("1", "Set up a researcher config (asks: how many researchers? 1-5)"),
    ("2", "Score a single test post (debug, no checkpoint)"),
    ("3", "Score a single batch (5 posts, integration test)"),
    ("4", "Run full pipeline for assigned universities"),
    ("5", "Resume from last checkpoint"),
    ("6", "Show progress / list checkpoints"),
    ("7", "Validate outputs (schema + range)"),
    ("8", "View / edit few-shot examples"),
    ("9", "Merge results across all researchers (lead only)"),
    ("0", "Quit"),
]


def main() -> int:
    ensure_dotenv()
    while True:
        choice = _menu("VAD Sentiment Scoring — Interactive Launcher", MENU)
        try:
            if choice == "1":
                action_setup_researcher()
            elif choice == "2":
                action_score_test_post()
            elif choice == "3":
                action_score_test_batch()
            elif choice == "4":
                action_run_full()
            elif choice == "5":
                action_resume()
            elif choice == "6":
                action_show_progress()
            elif choice == "7":
                action_validate_outputs()
            elif choice == "8":
                action_view_few_shot()
            elif choice == "9":
                action_merge()
            elif choice == "0":
                print("Bye.")
                return 0
        except KeyboardInterrupt:
            print("\nInterrupted; back to menu.")
        except Exception as e:
            print(f"\nERROR: {e}")
            traceback.print_exc()
            input("Press Enter to return to menu.")


if __name__ == "__main__":
    sys.exit(main())
