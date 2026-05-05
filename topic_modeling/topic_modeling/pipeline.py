"""Orchestrator for the topic_modeling phase.

End-to-end flow per plan §2:
  Stage 0: pre-flight (deps, GPU, API key, mapping, prompt SHA)
  Stage 1: optional embedding bake-off (SLU pilot, one-time)
  Stage 2: per-university BERTopic training (encode → grid → soft-reassign →
           keywords → rep-docs → DTM → persist)
  Stage 3: NIM API labeling per topic (with retries, validation, caching)
  Stage 4: per-researcher validation reports
"""
from __future__ import annotations

import os
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import cluster, dtm, embed, labeling, subcluster, summary, temporal, topics, validation
from .checkpoint import checkpoint_exists, write_checkpoint
from .dotenv import autoload as autoload_dotenv
from .io_utils import (append_jsonl, load_json, load_text_lines, load_yaml,
                       sha256_file, sha256_text, write_json)
from .logging_setup import log_action, now_pht_iso, setup_logger
from .textprep import strip_placeholders_batch

log = setup_logger(__name__)


@dataclass
class TopicModelingConfig:
    root: Path
    bertopic_cfg: dict
    gpu_cfg: dict
    researcher_cfg: dict
    mapping: dict
    stopwords: list[str]
    prompt_template: str
    prompt_sha256: str
    input_dir: Path
    bakeoff_only: bool = False
    skip_bakeoff: bool = False
    extras: dict[str, Any] = field(default_factory=dict)


# --- Pre-flight ------------------------------------------------------------

def preflight_check(cfg: TopicModelingConfig) -> dict:
    issues: list[str] = []
    info: dict[str, Any] = {}

    # Load .env files (project_root/.env and topic_modeling/.env). Real env wins.
    loaded = autoload_dotenv(cfg.root)
    info["dotenv_loaded_keys"] = sorted(loaded.keys())

    # API key
    key_env = cfg.researcher_cfg["api_key_env_var"]
    api_key = os.environ.get(key_env)
    if not api_key and not cfg.bakeoff_only:
        issues.append(f"Env var {key_env} is not set (required for labeling stage)")
    info["api_key_present"] = bool(api_key)

    # GPU
    try:
        import torch
        info["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            info["cuda_device_name"] = torch.cuda.get_device_name(0)
            info["cuda_total_vram_mb"] = int(
                torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
            )
    except Exception as e:
        info["cuda_available"] = False
        info["cuda_error"] = str(e)

    # Mapping coverage for assigned files
    assigned = cfg.researcher_cfg.get("assigned_files", [])
    info["assigned_files"] = list(assigned)
    unmapped = []
    inactive = []
    for fn in assigned:
        m = cfg.mapping.get("mappings", {}).get(fn)
        if m is None:
            unmapped.append(fn)
            continue
        if not m.get("active", True):
            inactive.append(fn)
        if str(m.get("code", "")).upper() == "TBD":
            unmapped.append(fn)
    if unmapped:
        issues.append(f"Files unmapped or TBD in university_mapping.yaml: {unmapped}")
    if inactive:
        issues.append(f"Files marked active=false in university_mapping.yaml: {inactive}")

    # Prompt SHA freeze
    expected = cfg.bertopic_cfg.get("labeling_prompt_sha256")
    info["prompt_sha256"] = cfg.prompt_sha256
    if expected == "TBD_AT_FIRST_RUN_AND_FROZEN":
        issues.append(
            "labeling_prompt_sha256 not yet frozen. Pre-flight will write the current "
            "SHA (informational); freeze it manually before the production run."
        )
    elif expected and expected != cfg.prompt_sha256:
        issues.append(
            f"Prompt drift: expected {expected}, got {cfg.prompt_sha256}. "
            "Restore configs/prompts/labeling_prompt.txt or update the frozen hash."
        )

    info["issues"] = issues
    return info


# --- Stage 1: bake-off -----------------------------------------------------

def run_bakeoff(cfg: TopicModelingConfig) -> str:
    """Run the embedding bake-off on the SLU pilot, persist the winner to
    bertopic_config.json, and return the chosen model name."""
    pilot_file = cfg.input_dir / "SLU_cleaned.json"
    if not pilot_file.exists():
        raise FileNotFoundError(f"Pilot corpus not found: {pilot_file}")
    posts = load_json(pilot_file)
    docs = [p["text"] for p in posts]
    log.info("Bake-off pilot loaded: %d posts from %s", len(docs), pilot_file)

    def cluster_eval(embeddings, eval_docs):
        # Fixed clustering for fair comparison: UMAP defaults + HDBSCAN(50, 10)
        reduced = cluster.run_umap(
            embeddings,
            n_neighbors=cfg.bertopic_cfg["umap"]["n_neighbors"],
            n_components=cfg.bertopic_cfg["umap"]["n_components"],
            metric=cfg.bertopic_cfg["umap"]["metric"],
            min_dist=cfg.bertopic_cfg["umap"]["min_dist"],
            random_state=cfg.bertopic_cfg["umap"]["random_state"],
        )
        _, lbls = cluster.run_hdbscan(
            reduced, min_cluster_size=50, min_samples=10,
            metric=cfg.bertopic_cfg["hdbscan_static"]["metric"],
            cluster_selection_method=cfg.bertopic_cfg["hdbscan_static"]["cluster_selection_method"],
        )
        return {
            "outlier_rate": cluster.outlier_rate(lbls),
            "silhouette": cluster.silhouette_for_clusters(reduced, lbls),
            "npmi": cluster.fast_npmi(eval_docs, lbls),
        }

    report_path = cfg.root / "validation" / "embedding_bakeoff_report.md"
    winner, report = embed.run_embedding_bakeoff(
        cfg.bertopic_cfg, docs, cluster_eval=cluster_eval, write_report_path=report_path,
    )
    log.info("Bake-off winner: %s", winner)

    # Persist winner to bertopic_config.json
    cfg.bertopic_cfg["embedding_model_id"] = winner
    write_json(cfg.root / "configs" / "bertopic_config.json", cfg.bertopic_cfg)

    log_action(
        cfg.root / "action_log.md",
        action_type="EMBEDDING_BAKEOFF",
        title=f"Bake-off complete — winner: {winner}",
        action="Compared MiniLM vs XLM-RoBERTa-Large on SLU pilot.",
        configuration={
            "umap": cfg.bertopic_cfg["umap"],
            "hdbscan": {"min_cluster_size": 50, "min_samples": 10},
            "margin_pct": report["margin_pct"],
        },
        inputs={"pilot_file": str(pilot_file), "n_posts": len(docs)},
        outputs=report["results"],
        decisions=f"Locked embedding_model_id = {winner}.",
        next_steps="Run per-university training across assigned files.",
    )
    return winner


# --- Stage 2-4: per-university loop ----------------------------------------

def process_university(cfg: TopicModelingConfig, fname: str, *, embedder) -> dict | None:
    """Train + label one university. Returns the assessment dict (or None on skip)."""
    mapping_entry = cfg.mapping["mappings"][fname]
    univ_code = mapping_entry["code"]
    checkpoint_dir = cfg.root / cfg.researcher_cfg["checkpoint_dir"]

    if checkpoint_exists(checkpoint_dir, univ_code):
        log.info("Skipping %s — checkpoint exists", univ_code)
        log_action(cfg.root / "action_log.md", action_type="RESUME",
                   title=f"Resume — {univ_code} already complete",
                   action=f"Found checkpoint at {checkpoint_dir / (univ_code + '_state.json')}.",
                   inputs={"university_code": univ_code, "researcher": cfg.researcher_cfg["researcher_id"]})
        return None

    src = cfg.input_dir / fname
    posts = load_json(src)
    n_posts = len(posts)
    log.info("=== %s (%s) — %d posts ===", univ_code, fname, n_posts)

    if n_posts < cfg.bertopic_cfg["min_posts_per_university"]:
        log_action(cfg.root / "action_log.md", action_type="SKIP_LOW_VOLUME",
                   title=f"Skipped {univ_code} — too few posts ({n_posts})",
                   action=f"Posts {n_posts} < threshold {cfg.bertopic_cfg['min_posts_per_university']}.",
                   inputs={"file": fname, "n_posts": n_posts},
                   decisions="Skip; do not train BERTopic on undersized corpus.")
        return None

    raw_texts = [p["text"] for p in posts]
    docs = strip_placeholders_batch(raw_texts)   # PRONG 1: kill placeholder noise
    post_ids = [p["post_id"] for p in posts]
    timestamps = [p.get("timestamp_unix") for p in posts]

    # --- Encode ---
    encode_cfg = cfg.gpu_cfg
    initial = (encode_cfg["large_corpus_initial_batch"]
               if n_posts >= encode_cfg["large_corpus_threshold_posts"]
               else encode_cfg["encode_batch_initial"])
    halving = encode_cfg["encode_batch_halving_sequence"]

    oom_events: list[dict] = []
    def _on_oom(b_from, b_to):
        oom_events.append({"from": b_from, "to": b_to, "ts": now_pht_iso()})

    try:
        embeddings = embed.encode_with_oom_fallback(
            embedder, docs, initial_batch=initial,
            halving_sequence=halving, log_oom=_on_oom,
        )
    except Exception as e:
        if encode_cfg.get("cpu_fallback_allowed"):
            log.warning("GPU encode exhausted; falling back to CPU. %s", e)
            embeddings = embed.encode_on_cpu(
                cfg.bertopic_cfg["embedding_model_id"], docs,
                batch_size=encode_cfg.get("minilm_cpu_batch", 64),
            )
            log_action(cfg.root / "action_log.md", action_type="CPU_FALLBACK",
                       title=f"CPU fallback engaged for {univ_code}",
                       action="GPU OOM at minimum batch_size; switched to CPU.",
                       errors=str(e),
                       decisions="Quality unchanged but ~3-5x slower for this university.")
        else:
            raise

    # Record VRAM peak
    vram_path = cfg.root / "gpu_logs" / "vram_usage.jsonl"
    append_jsonl(vram_path, [{
        "univ_code": univ_code,
        "n_posts": n_posts,
        "vram_peak_mb": embed._vram_peak_mb(),
        "oom_events": oom_events,
        "ts": now_pht_iso(),
    }])
    embed._reset_vram_peak()

    # --- Grid search (PRONG 2: 3-tier size bucketing) ---
    if n_posts < 1500:
        grid_key = "small_corpus_under_1500"
    elif n_posts < 5000:
        grid_key = "medium_corpus_1500_to_5000"
    else:
        grid_key = "default"
    grid = cfg.bertopic_cfg["hdbscan_grid"][grid_key]
    best, all_results = cluster.grid_search_hdbscan(
        embeddings, docs,
        umap_cfg=cfg.bertopic_cfg["umap"],
        grid=grid,
        hdbscan_static=cfg.bertopic_cfg["hdbscan_static"],
        weights=cfg.bertopic_cfg["selection_score_weights"],
        min_cluster_count_floor=cfg.bertopic_cfg.get("min_cluster_count_floor", 0),
    )
    best.pop("_reduced", None)
    log_action(cfg.root / "action_log.md", action_type="GRID_SEARCH",
               title=f"HDBSCAN grid search — {univ_code}",
               configuration={"grid_key": grid_key, "grid": grid},
               inputs={"n_posts": n_posts, "embedding_dim": int(embeddings.shape[1])},
               outputs={"best": best, "all_results": all_results})

    # --- Build BERTopic with best params ---
    topic_model, raw_topics, probs = topics.build_bertopic(
        docs, embeddings,
        umap_cfg=cfg.bertopic_cfg["umap"],
        hdbscan_params={
            "min_cluster_size": best["min_cluster_size"],
            "min_samples": best["min_samples"],
            "metric": cfg.bertopic_cfg["hdbscan_static"]["metric"],
            "cluster_selection_method": cfg.bertopic_cfg["hdbscan_static"]["cluster_selection_method"],
        },
        stopwords=cfg.stopwords,
        ngram_range=tuple(cfg.bertopic_cfg["ctf_idf"]["ngram_range"]),
    )

    # --- Soft reassignment ---
    new_topics, soft_stats = topics.soft_reassign_outliers(
        raw_topics, probs, threshold=cfg.bertopic_cfg["soft_reassignment_threshold"],
    )
    reassigned_idx = {i for i in range(len(raw_topics))
                      if raw_topics[i] == -1 and new_topics[i] != -1}

    # --- PRONG 4: sub-cluster any cluster holding > 20% of corpus ---
    dump_clusters = subcluster.find_dump_clusters(new_topics)
    subcluster_log: list[dict] = []
    any_real_split = False
    if dump_clusters:
        log.info("Dump clusters detected: %s — running sub-clustering pass", dump_clusters)
        # We need UMAP-reduced rows. Re-running UMAP on the embeddings would be
        # ideal but expensive; for HDBSCAN sub-clustering on the dump cluster
        # we use the raw embeddings directly (HDBSCAN handles high-dim okay
        # for the small subset).
        for dc_id in dump_clusters:
            member_mask = new_topics == dc_id
            member_emb = embeddings[member_mask]
            # Use outlier_recovery params for the sub-pass
            recovery = cfg.bertopic_cfg["hdbscan_grid"]["outlier_recovery"]
            sub_labels = subcluster.subcluster_hdbscan(
                member_emb,
                min_cluster_size=recovery["min_cluster_size"][0],
                min_samples=recovery["min_samples"][0],
            )
            next_id = int(new_topics.max()) + 1
            new_topics, info = subcluster.merge_subclusters_back(
                new_topics, dc_id, sub_labels, next_topic_id=next_id,
            )
            subcluster_log.append(info)
            if not info.get("skipped", False):
                any_real_split = True
            log_action(cfg.root / "action_log.md", action_type="SUBCLUSTER",
                       title=f"Sub-clustered dump cluster {dc_id} in {univ_code}",
                       configuration={"recovery_params": recovery},
                       outputs=info)

    # If sub-clustering actually changed the assignments, BERTopic's internal
    # get_topics()/get_representative_docs() are stale — they still reflect the
    # PRE-sub-cluster state. update_topics() recomputes c-TF-IDF and rep docs
    # from the new label array so keywords/rep_docs/labels can be extracted for
    # the new sub-cluster IDs.
    if any_real_split:
        log.info("Sub-clustering changed labels — refreshing BERTopic c-TF-IDF via update_topics")
        try:
            topic_model.update_topics(docs, topics=new_topics.tolist(),
                                      vectorizer_model=topic_model.vectorizer_model)
        except Exception as e:
            log.warning("update_topics failed (%s); proceeding with stale BERTopic state", e)

    # --- Topic-count reduction: if the grid + sub-clustering produced too many
    #     fragmented topics (e.g. MM-PSEC-1 with min_samples=2 producing 40+),
    #     merge similar topics by c-TF-IDF cosine similarity down to target.
    n_topics_now = len({t for t in new_topics.tolist() if t != -1})
    reduce_threshold = cfg.bertopic_cfg.get("reduce_topics_threshold", 0)
    target_count = cfg.bertopic_cfg.get("target_topic_count", 15)
    if reduce_threshold and n_topics_now > reduce_threshold:
        log.info("Topic count %d exceeds reduce_topics_threshold %d — merging to target %d",
                 n_topics_now, reduce_threshold, target_count)
        try:
            topic_model.reduce_topics(docs, nr_topics=target_count)
            # After reduce_topics, BERTopic updates its internal topics_ attribute.
            new_topics = np.asarray(topic_model.topics_)
            log_action(cfg.root / "action_log.md", action_type="REDUCE_TOPICS",
                       title=f"Reduced topics in {univ_code} from {n_topics_now} → {len({t for t in new_topics.tolist() if t != -1})}",
                       configuration={"target_topic_count": target_count,
                                      "reduce_threshold": reduce_threshold},
                       outputs={"n_topics_before": n_topics_now,
                                "n_topics_after": len({t for t in new_topics.tolist() if t != -1})})
        except Exception as e:
            log.warning("reduce_topics failed (%s); keeping pre-reduction labels", e)

    final_outlier_rate = float((new_topics == -1).mean())

    # --- Outlier recovery ---
    if final_outlier_rate > cfg.bertopic_cfg["outlier_rate_warning_threshold"]:
        log_action(cfg.root / "action_log.md", action_type="OUTLIER_HIGH",
                   title=f"OUTLIER_HIGH — {univ_code} ({final_outlier_rate:.2%})",
                   action="Outlier rate exceeds threshold; flagged for human review.",
                   configuration={"hdbscan_params": best,
                                  "soft_threshold": cfg.bertopic_cfg["soft_reassignment_threshold"]},
                   outputs={"final_outlier_rate": final_outlier_rate,
                            "soft_stats": soft_stats},
                   decisions="Persisting result; recommend rerun with hdbscan_grid.outlier_recovery.",
                   next_steps="Manual review of outlier_report.json.")

    # --- Keywords + rep docs ---
    keywords = topics.extract_keywords(topic_model, top_n=10)
    rep_docs = topics.extract_representative_docs(topic_model, docs, post_ids, top_n=5)

    # --- DTM ---
    dtm_out = dtm.run_dtm(topic_model, docs, timestamps,
                          min_bins=cfg.bertopic_cfg["dtm"]["min_bins"])

    # --- Persist clustering outputs ---
    out_dir = cfg.root / "outputs" / univ_code
    write_json(out_dir / "topic_assignments.json",
               topics.serialize_assignments(post_ids, new_topics, probs, reassigned_idx))
    write_json(out_dir / "topic_keywords.json",
               {str(tid): [{"word": w, "score": s} for w, s in kws]
                for tid, kws in keywords.items()})
    write_json(out_dir / "topic_rep_docs.json",
               {str(tid): docs_ for tid, docs_ in rep_docs.items()})
    write_json(out_dir / "topics_over_time.json", dtm_out)

    metadata = topics.topic_metadata(
        new_topics, npmi=best["npmi"], silhouette=best["silhouette"],
        outlier_rate=final_outlier_rate,
        hdbscan_params={"min_cluster_size": best["min_cluster_size"],
                        "min_samples": best["min_samples"]},
    )
    metadata["soft_stats"] = soft_stats
    write_json(out_dir / "topic_metadata.json", metadata)

    # --- Persist model ---
    model_path = cfg.root / "models" / f"{univ_code}_bertopic_model.pkl"
    topics.save_model(topic_model, model_path)

    # --- PRONG 3: temporal-concentration scoring per topic ---
    corpus_months = temporal.corpus_month_keys(timestamps)
    timestamps_arr = np.asarray(timestamps, dtype=object)
    topic_signatures: dict[int, dict] = {}
    for tid in sorted(set(int(t) for t in new_topics)):
        if tid == -1:
            continue
        member_ts = timestamps_arr[new_topics == tid].tolist()
        topic_signatures[tid] = temporal.cluster_temporal_signature(member_ts, corpus_months)

    # --- PRONG 5: per-university acronym glossary ---
    acronyms = labeling.load_acronyms_for_university(cfg.root / "configs", univ_code)
    if acronyms:
        log.info("Loaded %d acronyms for %s", len(acronyms), univ_code)

    # --- Stage 3: NIM labeling (skipped if bakeoff_only) ---
    label_records: list[dict] = []
    if not cfg.bakeoff_only:
        api_key = os.environ[cfg.researcher_cfg["api_key_env_var"]]
        rate_limiter = labeling.TokenBucket(cfg.researcher_cfg.get("effective_rpm", 40))
        client = labeling.NimClient(
            api_key=api_key,
            endpoint=cfg.researcher_cfg["model_endpoint"],
            model_id=cfg.researcher_cfg["model_id"],
            temperature=cfg.researcher_cfg["temperature"],
            max_tokens=cfg.researcher_cfg["max_tokens"],
            request_timeout=cfg.researcher_cfg["request_timeout_seconds"],
            max_retries=cfg.researcher_cfg["max_retries"],
            backoff_min=cfg.researcher_cfg["retry_backoff_min_seconds"],
            backoff_max=cfg.researcher_cfg["retry_backoff_max_seconds"],
            rate_limiter=rate_limiter,
        )
        try:
            for tid in sorted(keywords.keys()):
                kw_words = [w for w, _ in keywords[tid]]
                rd = rep_docs.get(tid, [])
                sig = topic_signatures.get(tid, {})
                temporal_hint = (temporal.format_date_range(sig.get("concentrated_months", []))
                                 if sig.get("is_event_driven") else None)
                rec = labeling.label_topic(
                    client, cfg.prompt_template,
                    univ_code=univ_code, topic_id=tid,
                    keywords=kw_words, rep_docs=rd,
                    cache_dir=cfg.root / "api_cache" / "labeling_responses",
                    acronyms=acronyms or None,
                    temporal_hint=temporal_hint,
                )
                rec["temporal_signature"] = sig
                if temporal_hint:
                    rec.setdefault("flags", []).append("EVENT_DRIVEN")
                label_records.append(rec)
            label_records = labeling.dedupe_labels_intra_univ(label_records, keywords)
        finally:
            client.close()

    write_json(out_dir / "topic_labels.json", label_records)

    # --- Assess + checkpoint ---
    assessment = validation.assess_university(
        univ_code=univ_code, n_posts=n_posts, metadata=metadata, labels=label_records,
        cache_dir=cfg.root / "api_cache" / "labeling_responses", cfg=cfg.bertopic_cfg,
    )

    write_checkpoint(
        cfg.root / cfg.researcher_cfg["checkpoint_dir"],
        univ_code,
        researcher_id=cfg.researcher_cfg["researcher_id"],
        n_posts=n_posts,
        n_topics=metadata["n_topics"],
        outlier_rate=final_outlier_rate,
        bakeoff_winner=cfg.bertopic_cfg["embedding_model_id"],
        extras={"hdbscan_params": metadata["hdbscan_params"], "needs_review": assessment["needs_review"]},
    )

    log_action(cfg.root / "action_log.md", action_type="UNIV_COMPLETE",
               title=f"Completed {univ_code}",
               action=f"Trained BERTopic, labeled {len(label_records)} topics, ran DTM.",
               configuration={"hdbscan": metadata["hdbscan_params"],
                              "embedding_model": cfg.bertopic_cfg["embedding_model_id"]},
               inputs={"n_posts": n_posts, "file": fname},
               outputs={"n_topics": metadata["n_topics"],
                        "outlier_rate": final_outlier_rate,
                        "lazy_pct": assessment["checks"]["lazy_label_pct"],
                        "needs_review": assessment["needs_review"]})
    return assessment


# --- Top-level entry -------------------------------------------------------

def run(cfg: TopicModelingConfig) -> dict:
    started = time.perf_counter()
    info = preflight_check(cfg)
    log_action(cfg.root / "action_log.md", action_type="PREFLIGHT",
               title="Pre-flight environment check",
               configuration={"researcher_id": cfg.researcher_cfg["researcher_id"]},
               inputs={"input_dir": str(cfg.input_dir),
                       "assigned_files": cfg.researcher_cfg["assigned_files"]},
               outputs={k: v for k, v in info.items() if k != "issues"},
               errors=info["issues"] or None)
    if info["issues"]:
        # Only fail hard on the truly blocking issues; informational ones are logged.
        blocking = [i for i in info["issues"]
                    if "not set" in i or "unmapped" in i or "drift" in i or "active=false" in i]
        if blocking:
            raise RuntimeError(f"Pre-flight failed: {blocking}")

    # Stage 1: bake-off (one-time per project)
    if not cfg.skip_bakeoff and cfg.bertopic_cfg.get("embedding_model_id") in (None, "TBD_FROM_BAKEOFF"):
        run_bakeoff(cfg)
    if cfg.bakeoff_only:
        return {"bakeoff_only": True, "winner": cfg.bertopic_cfg["embedding_model_id"]}

    # Load embedder once for all universities
    embedder, _, _ = embed.load_embedder(cfg.bertopic_cfg)

    assessments: list[dict] = []
    all_labels_by_univ: dict[str, list[dict]] = {}
    for fname in cfg.researcher_cfg["assigned_files"]:
        try:
            assess = process_university(cfg, fname, embedder=embedder)
            if assess is None:
                continue
            assessments.append(assess)
            labels = load_json(cfg.root / "outputs" / cfg.mapping["mappings"][fname]["code"]
                               / "topic_labels.json")
            all_labels_by_univ[cfg.mapping["mappings"][fname]["code"]] = labels
        except Exception as e:
            log_action(cfg.root / "action_log.md", action_type="UNIV_FAILED",
                       title=f"FAILED {fname}",
                       action="Exception raised; continuing with next university.",
                       errors={"error": str(e), "traceback": traceback.format_exc()},
                       decisions="Do not abort whole run; reprocess later.")
            continue

    # --- Final reports ---
    val_dir = cfg.root / "validation"
    validation.write_outlier_report(val_dir / "outlier_report.json", assessments)
    validation.write_lazy_label_flags(val_dir / "lazy_label_flags.json", all_labels_by_univ)
    validation.intra_researcher_label_check(
        val_dir / "label_consistency_check.json", all_labels_by_univ)

    # Cross-university comparison: human-readable summary across ALL active mappings,
    # not just this researcher's. Surfaces topic-count variation as a thesis finding
    # rather than a hidden inconsistency.
    summary.write_cross_university_summary(
        root=cfg.root,
        outputs_dir=cfg.root / "outputs",
        mapping=cfg.mapping,
        input_dir=cfg.input_dir,
        summary_path=val_dir / "cross_university_summary.md",
    )

    elapsed = time.perf_counter() - started
    log_action(cfg.root / "action_log.md", action_type="RUN_COMPLETE",
               title=f"Run complete for {cfg.researcher_cfg['researcher_id']}",
               outputs={"n_universities_processed": len(assessments),
                        "wall_seconds": round(elapsed, 1),
                        "needs_review_count": sum(1 for a in assessments if a["needs_review"])})
    return {
        "n_universities_processed": len(assessments),
        "assessments": assessments,
        "wall_seconds": elapsed,
    }


def load_config_bundle(root: Path, researcher_id: str,
                       *, bakeoff_only: bool = False,
                       skip_bakeoff: bool = False) -> TopicModelingConfig:
    """Load all configs from disk into a TopicModelingConfig."""
    bertopic_cfg = load_json(root / "configs" / "bertopic_config.json")
    gpu_cfg = load_json(root / "configs" / "gpu_config.json")
    researcher_cfg = load_json(root / "configs" / f"{researcher_id}.json")
    mapping = load_yaml(root / "configs" / "university_mapping.yaml")
    stopwords = load_text_lines(root / "configs" / "stopwords_taglish.txt")
    prompt_path = root / "configs" / "prompts" / "labeling_prompt.txt"
    prompt_template = prompt_path.read_text(encoding="utf-8")
    prompt_sha256 = sha256_text(prompt_template)
    # Default input_dir = sibling preprocessing/output/
    input_dir = (root.parent / "preprocessing" / "output").resolve()
    return TopicModelingConfig(
        root=root,
        bertopic_cfg=bertopic_cfg,
        gpu_cfg=gpu_cfg,
        researcher_cfg=researcher_cfg,
        mapping=mapping,
        stopwords=stopwords,
        prompt_template=prompt_template,
        prompt_sha256=prompt_sha256,
        input_dir=input_dir,
        bakeoff_only=bakeoff_only,
        skip_bakeoff=skip_bakeoff,
    )
