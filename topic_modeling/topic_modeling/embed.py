"""Embedding model loading + bake-off + OOM-safe encoding.

The bake-off compares paraphrase-multilingual-MiniLM-L12-v2 (CPU-friendly,
proposal-approved) against FacebookAI/xlm-roberta-large (GPU-mandatory, more
expressive on Taglish per Cosme & De Leon 2024) on the SLU pilot. Decision
rule: lower outlier rate wins; tie-broken by NPMI; XLM-R-L must beat MiniLM
by >=5% on both metrics or MiniLM is retained for reproducibility.

Outside of bake-off, callers use load_embedder(cfg) + encode_with_oom_fallback()
to encode arbitrary documents.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .logging_setup import setup_logger

log = setup_logger(__name__)


@dataclass
class EmbeddingResult:
    """One side of a bake-off — keeps everything needed to decide a winner."""
    candidate_key: str
    model_name: str
    device: str
    batch_size: int
    embeddings_shape: tuple[int, int]
    encode_seconds: float
    vram_peak_mb: float | None


# --- Loader -----------------------------------------------------------------

def load_embedder(cfg: dict, candidate_key: str | None = None):
    """Instantiate a SentenceTransformer for a given candidate.

    cfg: the full bertopic_config.json dict.
    candidate_key: one of the keys under cfg["embedding_candidates"]; if None,
        looks up cfg["embedding_model_id"] (which is set after the bake-off).
    """
    from sentence_transformers import SentenceTransformer  # local import (heavy)
    import torch

    if candidate_key is None:
        chosen = cfg.get("embedding_model_id")
        if not chosen or chosen == "TBD_FROM_BAKEOFF":
            raise RuntimeError(
                "embedding_model_id is not yet set. Run the bake-off first "
                "(`python -m topic_modeling.run --bakeoff-only`)."
            )
        # Resolve the candidate_key from the chosen model name.
        for key, spec in cfg["embedding_candidates"].items():
            if spec["name"] == chosen:
                candidate_key = key
                break
        else:
            raise RuntimeError(f"embedding_model_id={chosen} not in embedding_candidates")

    spec = cfg["embedding_candidates"][candidate_key]
    pref = spec["device_preference"]
    device = "cuda" if (pref == "cuda" and torch.cuda.is_available()) else "cpu"
    if pref == "cuda" and device == "cpu":
        log.warning(
            "Candidate %s requested cuda but cuda is unavailable; falling back to cpu",
            candidate_key,
        )
    log.info(
        "Loading embedder %s on %s (free VRAM: %s MB)",
        spec["name"], device, _free_vram_mb()
    )
    model = SentenceTransformer(spec["name"], device=device)
    return model, candidate_key, device


# --- Encoding with OOM fallback --------------------------------------------

def encode_with_oom_fallback(
    model,
    docs: list[str],
    *,
    initial_batch: int,
    halving_sequence: list[int],
    log_oom: Callable[[int, int], None] | None = None,
):
    """Encode docs, halving batch_size on torch.cuda.OutOfMemoryError.

    Returns the embeddings array. Raises if even the smallest batch OOMs and
    the caller hasn't enabled CPU fallback (handled by the orchestrator).
    """
    import torch

    sequence = [b for b in halving_sequence if b <= initial_batch]
    if not sequence or sequence[0] != initial_batch:
        sequence = [initial_batch] + [b for b in halving_sequence if b < initial_batch]
    last_err: Exception | None = None
    for batch in sequence:
        try:
            log.info("Encoding %d docs at batch_size=%d", len(docs), batch)
            return model.encode(
                docs,
                batch_size=batch,
                show_progress_bar=True,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        except torch.cuda.OutOfMemoryError as e:
            last_err = e
            log.warning("CUDA OOM at batch_size=%d; reducing", batch)
            if log_oom is not None:
                next_batch = sequence[sequence.index(batch) + 1] if sequence.index(batch) + 1 < len(sequence) else batch
                log_oom(batch, next_batch)
            torch.cuda.empty_cache()
            continue
    assert last_err is not None
    raise last_err


def encode_on_cpu(model_name: str, docs: list[str], batch_size: int = 64):
    """Last-resort CPU encode. Loads a fresh CPU instance to free VRAM."""
    from sentence_transformers import SentenceTransformer
    log.warning(
        "CPU fallback engaged for %s (3-5x slower); consider re-running with "
        "more VRAM headroom", model_name
    )
    cpu_model = SentenceTransformer(model_name, device="cpu")
    return cpu_model.encode(
        docs,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )


# --- Bake-off ---------------------------------------------------------------

def run_embedding_bakeoff(
    cfg: dict,
    pilot_docs: list[str],
    *,
    cluster_eval: Callable[[Any, list[str]], dict],
    write_report_path: Path,
    margin_pct: float = 0.05,
) -> tuple[str, dict]:
    """Run both candidates on the pilot corpus, score, pick a winner.

    cluster_eval(embeddings, docs) -> {"outlier_rate": float, "npmi": float,
    "silhouette": float}. The orchestrator passes a thin wrapper around
    cluster.fixed_hdbscan_eval so this module stays clustering-agnostic.

    Returns (winner_model_name, full_report_dict).
    """
    import time
    results: dict[str, dict] = {}

    for key in ("minilm", "xlm_roberta_large"):
        spec = cfg["embedding_candidates"][key]
        log.info("=== Bake-off candidate: %s ===", key)
        model, _, device = load_embedder(cfg, candidate_key=key)
        t0 = time.perf_counter()
        try:
            embeddings = encode_with_oom_fallback(
                model,
                pilot_docs,
                initial_batch=spec["encode_batch_size"],
                halving_sequence=[spec["encode_batch_size"], spec["encode_batch_size"] // 2,
                                  max(spec["encode_batch_size"] // 4, 4)],
            )
        except Exception as e:
            log.error("Candidate %s failed during encode: %s", key, e)
            results[key] = {"error": str(e)}
            continue
        elapsed = time.perf_counter() - t0
        metrics = cluster_eval(embeddings, pilot_docs)
        results[key] = {
            "model_name": spec["name"],
            "device": device,
            "encode_seconds": round(elapsed, 1),
            "encode_batch_size": spec["encode_batch_size"],
            "vram_peak_mb": _vram_peak_mb(),
            **metrics,
        }
        _reset_vram_peak()

    winner = _pick_winner(results, margin_pct=margin_pct)
    _write_bakeoff_report(write_report_path, results, winner, margin_pct)
    return winner, {"results": results, "winner": winner, "margin_pct": margin_pct}


def _pick_winner(results: dict[str, dict], *, margin_pct: float) -> str:
    """Decision rule: lower outlier wins; if XLM-R-L beats MiniLM by less than
    margin_pct on BOTH outlier_rate and npmi, MiniLM is retained."""
    minilm = results.get("minilm")
    xlm = results.get("xlm_roberta_large")
    if minilm is None or "error" in minilm:
        if xlm is None or "error" in xlm:
            raise RuntimeError("Bake-off: both candidates failed")
        return xlm["model_name"]
    if xlm is None or "error" in xlm:
        return minilm["model_name"]

    out_diff = minilm["outlier_rate"] - xlm["outlier_rate"]   # >0 means XLM better
    npmi_diff = xlm["npmi"] - minilm["npmi"]                  # >0 means XLM better
    xlm_wins_outlier_by = out_diff / max(minilm["outlier_rate"], 1e-9)
    xlm_wins_npmi_by = npmi_diff / max(abs(minilm["npmi"]), 1e-9)
    if xlm_wins_outlier_by >= margin_pct and xlm_wins_npmi_by >= margin_pct:
        return xlm["model_name"]
    return minilm["model_name"]


def _write_bakeoff_report(path: Path, results: dict, winner: str, margin_pct: float) -> None:
    lines = [
        "# Embedding Bake-off Report",
        "",
        f"**Winner:** `{winner}`",
        f"**Decision margin:** XLM-R-Large must beat MiniLM by ≥{margin_pct*100:.0f}% on BOTH "
        "outlier_rate and NPMI; otherwise MiniLM is retained for reproducibility.",
        "",
        "## Metrics",
        "",
        "| Candidate | Model | Device | Outlier Rate | NPMI | Silhouette | Encode Time (s) | VRAM Peak (MB) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for key, r in results.items():
        if "error" in r:
            lines.append(f"| {key} | ERROR | — | — | — | — | — | — |")
            continue
        lines.append(
            f"| {key} | `{r['model_name']}` | {r['device']} | "
            f"{r['outlier_rate']:.3f} | {r['npmi']:.3f} | {r['silhouette']:.3f} | "
            f"{r['encode_seconds']:.1f} | {r.get('vram_peak_mb') or '—'} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- VRAM helpers (no-ops when CUDA unavailable) ----------------------------

def _free_vram_mb() -> int | None:
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        free, _ = torch.cuda.mem_get_info()
        return int(free // (1024 * 1024))
    except Exception:
        return None


def _vram_peak_mb() -> float | None:
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        return torch.cuda.max_memory_allocated() / (1024 * 1024)
    except Exception:
        return None


def _reset_vram_peak() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        pass
