"""Top-level orchestrator for the VAD scoring pipeline.

Run with:
    cfg = load_config_bundle(ROOT, researcher_id="researcher_2")
    run_university(cfg, "CAR-PSEC-1")
    # or to do all assigned universities sequentially:
    run_all(cfg)

Owns the per-university loop: load → batch → checkpoint-skip → PII-check →
prompt-build → API call → parse → reconcile → validate → write JSONL → save state.

All side-effects (validation logs, raw API cache, action_log entries) are wired
through here so the menu and tests can stay thin.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import batcher, checkpoint, pii_check, prompt as prompt_mod, validator
from .io_utils import append_jsonl, load_json, write_json
from .logging_setup import log_action, now_pht_iso, setup_logger
from .nim_client import (
    AuthError, CircuitBreaker, CircuitOpenError,
    NimClient, RateLimitError, TokenBucket, TransientAPIError,
)
from .parser import ParseError, parse_response

log = setup_logger(__name__)


# ---------------------------------------------------------------- config

@dataclass
class PipelineConfig:
    root: Path
    researcher_cfg: dict
    vad_cfg: dict
    few_shot_examples: list[dict]
    api_key: str
    mapping: dict[str, str]                  # {anon_code: source_filename}
    topic_outputs_dir: Path
    preprocessing_outputs_dir: Path
    action_log_path: Path
    validation_dir: Path
    api_cache_path: Path
    checkpoint_dir: Path
    output_dir: Path
    prompt_sha256: str

    @property
    def researcher_id(self) -> str:
        return self.researcher_cfg["researcher_id"]

    @property
    def assigned_universities(self) -> list[str]:
        return list(self.researcher_cfg.get("assigned_universities", []))


def load_config_bundle(root: Path, researcher_id: str) -> PipelineConfig:
    """Read all config files + env, validate, and return a frozen bundle."""
    configs_dir = root / "configs"

    vad_cfg = load_json(configs_dir / "vad_config.json")
    rcfg_path = configs_dir / f"{researcher_id}.json"
    if not rcfg_path.exists():
        raise FileNotFoundError(
            f"Researcher config not found: {rcfg_path}. "
            f"Run `python -m vad_scoring` option 1 to create one."
        )
    rcfg = load_json(rcfg_path)

    api_key_var = rcfg.get("api_key_env_var", "NVIDIA_NIM_API_KEY")
    api_key = os.environ.get(api_key_var, "").strip()
    if not api_key:
        raise RuntimeError(
            f"Environment variable {api_key_var} is empty. "
            f"Paste your key into vad_scoring/.env or run option 1 again."
        )

    few_shot = load_json(root / vad_cfg["few_shot_path"])["examples"]

    # The mapping file lives in topic_modeling/configs/. Resolve relative paths
    # against vad_scoring/.
    mapping_path = (root / vad_cfg["university_mapping_path"]).resolve()
    mapping = batcher.load_university_mapping(mapping_path)

    topic_outputs_dir = (root / vad_cfg["topic_modeling_outputs_dir"]).resolve()
    preprocessing_outputs_dir = (root / vad_cfg["preprocessing_outputs_dir"]).resolve()

    return PipelineConfig(
        root=root,
        researcher_cfg=rcfg,
        vad_cfg=vad_cfg,
        few_shot_examples=few_shot,
        api_key=api_key,
        mapping=mapping,
        topic_outputs_dir=topic_outputs_dir,
        preprocessing_outputs_dir=preprocessing_outputs_dir,
        action_log_path=root / "action_log.md",
        validation_dir=root / "validation",
        api_cache_path=root / rcfg["api_cache_path"],
        checkpoint_dir=root / rcfg["checkpoint_dir"],
        output_dir=root / rcfg["output_dir"],
        prompt_sha256=prompt_mod.compute_prompt_sha256(few_shot),
    )


# ---------------------------------------------------------------- helpers

def _make_client(cfg: PipelineConfig, *, api_cache_writer) -> NimClient:
    rcfg = cfg.researcher_cfg
    bucket = TokenBucket(rpm=int(rcfg.get("effective_rpm", 20)))
    breaker = CircuitBreaker(
        threshold=int(rcfg.get("circuit_breaker_consecutive_failures", 10)),
        pause_seconds=float(rcfg.get("circuit_breaker_pause_minutes", 5)) * 60.0,
    )
    return NimClient(
        api_key=cfg.api_key,
        endpoint=cfg.vad_cfg["model_endpoint"],
        model_id=cfg.vad_cfg["model_id"],
        temperature=float(cfg.vad_cfg.get("temperature", 0.1)),
        max_tokens=int(cfg.vad_cfg.get("max_tokens", 600)),
        request_timeout=float(rcfg.get("request_timeout_seconds", 30)),
        max_retries=int(rcfg.get("max_retries", 5)),
        backoff_min=float(rcfg.get("retry_backoff_min_seconds", 1)),
        backoff_max=float(rcfg.get("retry_backoff_max_seconds", 16)),
        rate_limiter=bucket,
        breaker=breaker,
        on_raw_response=api_cache_writer,
    )


def _make_api_cache_writer(path: Path):
    """Return a callable that appends each raw response to api_cache JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    def writer(record: dict) -> None:
        append_jsonl(path, [record])
    return writer


def _resolve_filename(cfg: PipelineConfig, univ_code: str) -> str:
    """Find the FW-NN_cleaned.json filename for a given anon code."""
    if univ_code not in cfg.mapping:
        raise KeyError(f"University code {univ_code} not in active mapping")
    return cfg.mapping[univ_code]


def _result_path(cfg: PipelineConfig, univ_code: str) -> Path:
    return cfg.output_dir / f"{univ_code}_vad_scores.jsonl"


def _compose_record(
    parsed: dict,
    expected: dict,
    *,
    researcher_id: str,
    model_version: str,
) -> dict:
    """Combine parsed VAD with the original batch metadata into a final output record."""
    return {
        "post_id": expected["post_id"],
        "univ_code": expected["univ_code"],
        "topic_id": expected["topic_id"],
        "topic_label": expected["topic_label"],
        "V": parsed["V"],
        "A": parsed["A"],
        "D": parsed["D"],
        "sarcasm": parsed["sarcasm"],
        "flags": parsed.get("flags", []),
        "researcher_id": researcher_id,
        "model_version": model_version,
        "scored_at": now_pht_iso(),
    }


# ---------------------------------------------------------------- core scoring

def score_one_batch(
    *,
    client: NimClient,
    batch: list[dict],
    few_shot: list[dict],
    scale_min: int,
    scale_max: int,
    max_repair_attempts: int = 3,
) -> tuple[list[dict], list[str], list[str]]:
    """Score a single batch and return (records, missing_post_ids, errors_list).

    Handles in-batch repair:
      - on ParseError: retry with stricter "ONLY a JSON array" reminder, up to
        max_repair_attempts times.
      - on duplicate IDs: retry the full batch once.
      - on length mismatch: report the missing IDs to the caller (which queues
        them as singles in the next pass).

    On AuthError or CircuitOpenError, the exception propagates — the caller
    decides whether to halt the whole pipeline or pause.
    """
    errors: list[str] = []
    messages = prompt_mod.build_messages(batch, few_shot)
    request_meta = {
        "post_ids": [p["post_id"] for p in batch],
        "univ_code": batch[0]["univ_code"] if batch else None,
        "batch_size": len(batch),
    }

    parsed: list[dict] = []
    model_version = client.model_id
    last_response_text = ""
    for attempt in range(1, max_repair_attempts + 1):
        try:
            content, meta = client.chat(messages, request_meta=request_meta)
            model_version = meta.get("model", model_version)
            last_response_text = content
            parsed = parse_response(content)
            break
        except ParseError as e:
            errors.append(f"parse-attempt-{attempt}: {e}")
            if attempt < max_repair_attempts:
                # Strengthen the instruction. Keep the original messages (we don't
                # want to leak intermediate state — just remind the model.)
                messages = list(messages)
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous response was not valid JSON. Reply with "
                        "ONLY a JSON array of 5 objects, no prose, no code fences."
                    ),
                })
                continue
            log.error("Batch %s: parse exhausted after %d attempts: %s",
                      request_meta["post_ids"], attempt, e)
            return [], [p["post_id"] for p in batch], errors

    rec_result = validator.reconcile_batch(parsed, batch)

    # Duplicates → log and continue with reconciled (last-occurrence wins)
    if rec_result.duplicate_ids:
        errors.append(f"duplicate_ids_in_response: {rec_result.duplicate_ids}")

    # Extras → log + drop (caller doesn't need to do anything)
    if rec_result.extra_ids:
        errors.append(f"extra_ids_in_response: {rec_result.extra_ids}")

    # Build final records (only for IDs that came back)
    records: list[dict] = []
    for expected in batch:
        if expected["post_id"] not in rec_result.reconciled:
            continue
        parsed_rec = rec_result.reconciled[expected["post_id"]]
        validator.clamp_and_check(parsed_rec, scale_min=scale_min, scale_max=scale_max)
        final = _compose_record(parsed_rec, expected,
                                researcher_id="",  # filled by caller
                                model_version=model_version)
        records.append(final)

    return records, rec_result.missing_ids, errors


# ---------------------------------------------------------------- per-university

def run_university(cfg: PipelineConfig, univ_code: str, *, dry_run_one_batch: bool = False) -> dict:
    """Score all posts for one university. Returns a summary dict."""
    fname = _resolve_filename(cfg, univ_code)
    cleaned_path = cfg.preprocessing_outputs_dir / fname
    assignments_path = cfg.topic_outputs_dir / univ_code / "topic_assignments.json"
    labels_path = cfg.topic_outputs_dir / univ_code / "topic_labels.json"

    for required in (cleaned_path, assignments_path, labels_path):
        if not required.exists():
            raise FileNotFoundError(f"Missing required input: {required}")

    log.info("[%s] loading inputs", univ_code)
    records = batcher.join_university(
        univ_code=univ_code,
        cleaned_path=cleaned_path,
        assignments_path=assignments_path,
        labels_path=labels_path,
        outlier_topic_label=cfg.vad_cfg.get("outlier_topic_label", "Unclassified"),
        max_post_chars=int(cfg.vad_cfg.get("max_post_chars", 1500)),
        truncation_suffix=cfg.vad_cfg.get("max_post_truncation_suffix", " [truncated]"),
    )

    # PII pre-check — reject before any API call.
    pii_violations_path = cfg.validation_dir / "pii_violations.jsonl"
    keep: list[dict] = []
    pii_rejects: list[dict] = []
    for r in records:
        hits = pii_check.detect_pii(r["text"])
        if hits:
            pii_rejects.append({
                "post_id": r["post_id"],
                "univ_code": univ_code,
                "hits": [{"kind": h.kind, "match": h.match} for h in hits],
                "rejected_at": now_pht_iso(),
            })
        else:
            keep.append(r)
    if pii_rejects:
        append_jsonl(pii_violations_path, pii_rejects)
        log.warning("[%s] %d posts rejected for PII; logged to %s",
                    univ_code, len(pii_rejects), pii_violations_path)

    batches = list(batcher.chunk_into_batches(keep, batch_size=int(cfg.vad_cfg.get("batch_size", 5))))
    total_batches = len(batches)
    log.info("[%s] %d posts → %d batches (after %d PII rejects)",
             univ_code, len(keep), total_batches, len(pii_rejects))

    # Resume support
    state = checkpoint.load_state(cfg.checkpoint_dir, univ_code)
    if state is None:
        state = checkpoint.initial_state(cfg.researcher_id, univ_code, total_batches)
    else:
        log.info("[%s] resuming from batch %d/%d",
                 univ_code, state["last_completed_batch"] + 1, total_batches)
        # If total_batches changed (e.g., topic_modeling re-ran), warn but proceed.
        if state.get("total_batches") != total_batches:
            log.warning("[%s] total_batches changed: was %d, now %d",
                        univ_code, state.get("total_batches"), total_batches)
            state["total_batches"] = total_batches

    completed_ids = checkpoint.load_completed_ids(cfg.checkpoint_dir, univ_code)
    state["pii_rejected_count"] = state.get("pii_rejected_count", 0) + len(pii_rejects)

    api_writer = _make_api_cache_writer(cfg.api_cache_path)
    client = _make_client(cfg, api_cache_writer=api_writer)
    out_path = _result_path(cfg, univ_code)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    range_anom_path = cfg.validation_dir / "range_anomalies.json"
    sarcasm_flags_path = cfg.validation_dir / "sarcasm_flags.json"

    range_anomalies: list[dict] = _load_json_list(range_anom_path)
    sarcasm_records: list[dict] = _load_json_list(sarcasm_flags_path)

    halted_reason: str | None = None
    start_index = state["last_completed_batch"] + 1
    iter_batches = list(enumerate(batches))[start_index:]
    if dry_run_one_batch:
        iter_batches = iter_batches[:1]
        log.info("[%s] DRY-RUN: scoring 1 batch only", univ_code)

    try:
        for batch_idx, batch in iter_batches:
            # Filter posts already scored on a previous run (defensive against
            # crashes mid-batch-write).
            pending = [p for p in batch if p["post_id"] not in completed_ids]
            if not pending:
                state["last_completed_batch"] = batch_idx
                continue

            try:
                records, missing, errs = score_one_batch(
                    client=client,
                    batch=pending,
                    few_shot=cfg.few_shot_examples,
                    scale_min=int(cfg.vad_cfg.get("scale_min", 1)),
                    scale_max=int(cfg.vad_cfg.get("scale_max", 9)),
                    max_repair_attempts=int(cfg.vad_cfg.get("max_in_batch_repair_attempts", 3)),
                )
            except AuthError as e:
                halted_reason = f"auth_error: {e}"
                log.error("HALTING: %s", e)
                break
            except CircuitOpenError as e:
                halted_reason = f"circuit_open: {e}"
                log.error("HALTING: %s", e)
                break
            except (RateLimitError, TransientAPIError) as e:
                # nim_client already retried; treat as fatal for this batch.
                state["failed_requests"] += 1
                state["failed_post_ids"].extend(p["post_id"] for p in pending)
                log.error("[%s] batch %d: API gave up: %s", univ_code, batch_idx, e)
                continue

            # Stamp researcher_id on each record (we left it blank in score_one_batch).
            for r in records:
                r["researcher_id"] = cfg.researcher_id

            # Persist records + completed ids
            if records:
                append_jsonl(out_path, records)
                new_ids = [r["post_id"] for r in records]
                checkpoint.append_completed_ids(cfg.checkpoint_dir, univ_code, new_ids)
                completed_ids.update(new_ids)

            # Side-effect logs
            for r in records:
                if "range_clamped" in r["flags"]:
                    state["out_of_range_clamps"] += 1
                    range_anomalies.append({
                        "post_id": r["post_id"], "univ_code": univ_code,
                        "V": r["V"], "A": r["A"], "D": r["D"],
                        "flags": r["flags"], "scored_at": r["scored_at"],
                    })
                if "sarcasm_high_valence" in r["flags"]:
                    state["sarcasm_flags"] += 1
                    sarcasm_records.append({
                        "post_id": r["post_id"], "univ_code": univ_code,
                        "V": r["V"], "A": r["A"], "D": r["D"],
                        "topic_label": r["topic_label"],
                        "scored_at": r["scored_at"],
                    })
                elif r["sarcasm"] is True:
                    state["sarcasm_flags"] += 1

            # Track failures by missing IDs
            if missing:
                state["failed_post_ids"].extend(missing)
                # de-dup, keep at most last 5000
                seen = set(); deduped = []
                for pid in reversed(state["failed_post_ids"]):
                    if pid not in seen:
                        seen.add(pid); deduped.append(pid)
                state["failed_post_ids"] = list(reversed(deduped))[-5000:]

            state["successful_requests"] += 1
            state["completed_post_ids_count"] = len(completed_ids)
            state["last_completed_batch"] = batch_idx

            if errs:
                log.warning("[%s] batch %d errors: %s", univ_code, batch_idx, errs)

            # Periodic checkpoint
            freq = int(cfg.vad_cfg.get("checkpoint_frequency_requests", 100))
            if state["successful_requests"] % freq == 0:
                checkpoint.save_state(cfg.checkpoint_dir, univ_code, state)
                _save_json_list(range_anom_path, range_anomalies)
                _save_json_list(sarcasm_flags_path, sarcasm_records)
                log_action(
                    cfg.action_log_path, "CHECKPOINT", f"{univ_code} progress",
                    action=f"Auto-checkpoint after {state['successful_requests']} requests",
                    outputs={
                        "univ_code": univ_code,
                        "batch": f"{batch_idx + 1}/{total_batches}",
                        "completed_post_ids": state["completed_post_ids_count"],
                        "out_of_range_clamps": state["out_of_range_clamps"],
                        "sarcasm_flags": state["sarcasm_flags"],
                    },
                )

    finally:
        # Always persist final state, anomalies, sarcasm.
        if not halted_reason and state["last_completed_batch"] + 1 >= total_batches:
            state["complete"] = True
        checkpoint.save_state(cfg.checkpoint_dir, univ_code, state)
        _save_json_list(range_anom_path, range_anomalies)
        _save_json_list(sarcasm_flags_path, sarcasm_records)
        client.close()

    summary = {
        "univ_code": univ_code,
        "total_batches": total_batches,
        "successful_requests": state["successful_requests"],
        "failed_requests": state["failed_requests"],
        "completed_post_ids": state["completed_post_ids_count"],
        "out_of_range_clamps": state["out_of_range_clamps"],
        "sarcasm_flags": state["sarcasm_flags"],
        "pii_rejected_count": state["pii_rejected_count"],
        "complete": state["complete"],
        "halted_reason": halted_reason,
    }
    if state["complete"]:
        log_action(
            cfg.action_log_path, "PIPELINE", f"{univ_code} scoring complete",
            action=f"University {univ_code} fully scored by {cfg.researcher_id}",
            outputs=summary,
        )
    return summary


def run_all(cfg: PipelineConfig, *, dry_run_one_batch: bool = False) -> list[dict]:
    """Run every assigned university sequentially. Returns list of summaries."""
    summaries: list[dict] = []
    for code in cfg.assigned_universities:
        log.info("=" * 60)
        log.info("Starting university %s", code)
        log.info("=" * 60)
        try:
            summary = run_university(cfg, code, dry_run_one_batch=dry_run_one_batch)
            summaries.append(summary)
            if summary.get("halted_reason"):
                log.error("Halted on %s: %s — stopping further universities.",
                          code, summary["halted_reason"])
                break
        except FileNotFoundError as e:
            log.error("Skipping %s: %s", code, e)
            summaries.append({"univ_code": code, "error": str(e)})
            continue
    return summaries


# ---------------------------------------------------------------- retry pass

def retry_failed_posts(cfg: PipelineConfig, univ_code: str) -> dict:
    """Re-attempt every post in the university's `failed_post_ids` set.

    Used when a university's first pass marked itself complete but with a
    non-empty failed_post_ids deque (i.e. some batches gave up after the 5-retry
    backoff exhausted). Loads the affected posts, re-batches them in groups of
    5, and runs them through score_one_batch. Posts that succeed on this pass
    are removed from failed_post_ids and appended to the result JSONL.

    Returns a summary dict.
    """
    state = checkpoint.load_state(cfg.checkpoint_dir, univ_code)
    if state is None:
        return {"univ_code": univ_code, "error": "no checkpoint state — run main pipeline first"}
    failed_ids = list(state.get("failed_post_ids", []))
    if not failed_ids:
        return {"univ_code": univ_code, "info": "no failed posts to retry", "n_failed": 0}

    completed_ids = checkpoint.load_completed_ids(cfg.checkpoint_dir, univ_code)
    failed_ids = [pid for pid in failed_ids if pid not in completed_ids]
    if not failed_ids:
        # All previously-failed posts were already recovered (e.g. from a prior retry).
        state["failed_post_ids"] = []
        checkpoint.save_state(cfg.checkpoint_dir, univ_code, state)
        return {"univ_code": univ_code, "info": "all previously-failed posts already recovered", "n_failed": 0}

    log.info("[%s] retrying %d failed posts in batches of 5", univ_code, len(failed_ids))

    # Reload the full records to recover post text + topic context for each failed ID
    fname = _resolve_filename(cfg, univ_code)
    cleaned_path = cfg.preprocessing_outputs_dir / fname
    assignments_path = cfg.topic_outputs_dir / univ_code / "topic_assignments.json"
    labels_path = cfg.topic_outputs_dir / univ_code / "topic_labels.json"
    all_records = batcher.join_university(
        univ_code=univ_code,
        cleaned_path=cleaned_path,
        assignments_path=assignments_path,
        labels_path=labels_path,
        outlier_topic_label=cfg.vad_cfg.get("outlier_topic_label", "Unclassified"),
        max_post_chars=int(cfg.vad_cfg.get("max_post_chars", 1500)),
        truncation_suffix=cfg.vad_cfg.get("max_post_truncation_suffix", " [truncated]"),
    )
    by_id = {r["post_id"]: r for r in all_records}
    to_retry = [by_id[pid] for pid in failed_ids if pid in by_id]
    skipped_missing_text = len(failed_ids) - len(to_retry)

    api_writer = _make_api_cache_writer(cfg.api_cache_path)
    client = _make_client(cfg, api_cache_writer=api_writer)
    out_path = _result_path(cfg, univ_code)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    range_anom_path = cfg.validation_dir / "range_anomalies.json"
    sarcasm_flags_path = cfg.validation_dir / "sarcasm_flags.json"
    range_anomalies = _load_json_list(range_anom_path)
    sarcasm_records = _load_json_list(sarcasm_flags_path)

    recovered = 0
    still_failed: list[str] = []
    halted_reason: str | None = None
    batches = list(batcher.chunk_into_batches(to_retry, batch_size=int(cfg.vad_cfg.get("batch_size", 5))))

    try:
        for batch_idx, batch in enumerate(batches):
            try:
                records, missing, errs = score_one_batch(
                    client=client, batch=batch, few_shot=cfg.few_shot_examples,
                    scale_min=int(cfg.vad_cfg.get("scale_min", 1)),
                    scale_max=int(cfg.vad_cfg.get("scale_max", 9)),
                    max_repair_attempts=int(cfg.vad_cfg.get("max_in_batch_repair_attempts", 3)),
                )
            except AuthError as e:
                halted_reason = f"auth_error: {e}"
                log.error("HALTING retry: %s", e)
                break
            except CircuitOpenError as e:
                halted_reason = f"circuit_open: {e}"
                log.error("HALTING retry: %s", e)
                break
            except (RateLimitError, TransientAPIError) as e:
                still_failed.extend(p["post_id"] for p in batch)
                log.error("[%s][retry] batch %d API gave up again: %s", univ_code, batch_idx, e)
                continue

            for r in records:
                r["researcher_id"] = cfg.researcher_id
            if records:
                append_jsonl(out_path, records)
                new_ids = [r["post_id"] for r in records]
                checkpoint.append_completed_ids(cfg.checkpoint_dir, univ_code, new_ids)
                completed_ids.update(new_ids)
                recovered += len(new_ids)

            for r in records:
                if "range_clamped" in r["flags"]:
                    state["out_of_range_clamps"] += 1
                    range_anomalies.append({
                        "post_id": r["post_id"], "univ_code": univ_code,
                        "V": r["V"], "A": r["A"], "D": r["D"],
                        "flags": r["flags"], "scored_at": r["scored_at"],
                    })
                if "sarcasm_high_valence" in r["flags"]:
                    sarcasm_records.append({
                        "post_id": r["post_id"], "univ_code": univ_code,
                        "V": r["V"], "A": r["A"], "D": r["D"],
                        "topic_label": r["topic_label"], "scored_at": r["scored_at"],
                    })
                if r.get("sarcasm") is True:
                    state["sarcasm_flags"] += 1

            still_failed.extend(missing)
            if errs:
                log.warning("[%s][retry] batch %d errors: %s", univ_code, batch_idx, errs)

    finally:
        # New failed_post_ids = posts that failed text lookup + posts that re-failed
        state["failed_post_ids"] = (
            [pid for pid in failed_ids if pid not in by_id]  # text-missing
            + [pid for pid in still_failed if pid not in completed_ids]
        )
        state["completed_post_ids_count"] = len(completed_ids)
        checkpoint.save_state(cfg.checkpoint_dir, univ_code, state)
        _save_json_list(range_anom_path, range_anomalies)
        _save_json_list(sarcasm_flags_path, sarcasm_records)
        client.close()

    summary = {
        "univ_code": univ_code,
        "n_originally_failed": len(failed_ids),
        "n_recovered": recovered,
        "n_still_failed": len(state["failed_post_ids"]),
        "skipped_missing_text": skipped_missing_text,
        "halted_reason": halted_reason,
    }
    log_action(
        cfg.action_log_path, "PIPELINE_RETRY", f"{univ_code} failed-posts retry",
        action=f"Retried {len(failed_ids)} previously-failed posts in {univ_code}",
        outputs=summary,
    )
    return summary


# ---------------------------------------------------------------- json list helpers

def _load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = load_json(path)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_json_list(path: Path, items: list[dict]) -> None:
    write_json(path, items)
