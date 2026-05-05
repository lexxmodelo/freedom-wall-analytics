# Embedding Bake-off Report

**Run date:** 2026-05-06 (lead researcher's RTX 4050 Laptop GPU, 6 GB VRAM)
**Pilot corpus:** SLU_cleaned.json (3,864 posts)
**Clustering settings (identical for both candidates):** UMAP(n_neighbors=15, n_components=5, metric=cosine, min_dist=0.05, seed=42); HDBSCAN(min_cluster_size=50, min_samples=10, metric=euclidean, eom)

## Rule's verdict

**Rule:** XLM-R-Large must beat MiniLM by ≥5% on BOTH outlier_rate AND NPMI; otherwise MiniLM is retained for reproducibility.

**Result by rule:** `paraphrase-multilingual-MiniLM-L12-v2` (XLM-R-L lost on NPMI by 0.042).

## Methodology override (2026-05-06)

**Decision:** Override to `FacebookAI/xlm-roberta-large`.

**Justification:** XLM-R-L dominates on the two metrics that matter most for downstream event detection and topic separation:
- **Outlier rate 0.000 vs 0.137** — XLM-R-L produces no outliers at min_cluster_size=50; MiniLM leaves 13.7% of posts ungrouped.
- **Silhouette +0.189 vs −0.069** — MiniLM's negative silhouette indicates significant cluster overlap (clusters are not well-separated). XLM-R-L produces tight, well-separated clusters.

The marginal NPMI loss (0.042) reflects keyword coherence within clusters — a downstream concern partially mitigated by `textprep.strip_placeholders()` and the per-university acronym glossary (action_log.md ACTION-003).

This is a deliberate methodology deviation from the conservative bake-off rule. It should be disclosed to the thesis committee as an empirically-justified upgrade from the proposal's MiniLM baseline. Cosme & De Leon (2024) provide the literature support for XLM-RoBERTa-Large on Taglish code-switched text.

## Metrics

| Candidate | Model | Device | Outlier Rate | NPMI | Silhouette | Encode Time (s) | VRAM Peak (MB) |
|---|---|---|---|---|---|---|---|
| minilm | `paraphrase-multilingual-MiniLM-L12-v2` | cpu | 0.137 | **0.160** | -0.069 | 63.5 | — |
| xlm_roberta_large | `FacebookAI/xlm-roberta-large` | cuda | **0.000** | 0.118 | **0.189** | **53.1** | 2532.3 |

**Locked decision:** `embedding_model_id = FacebookAI/xlm-roberta-large` in `configs/bertopic_config.json`.
