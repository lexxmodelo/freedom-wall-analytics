# Cross-University Topic Modeling Summary

_Generated 2026-05-05 19:22 UTC_

Universities completed: **3** of 10

## Completed universities

| Code | Alias | Region | Posts | Top languages | Date range | Topics | Outlier % | NPMI | Silhouette | Lazy labels % | Event-driven % | API fails |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `MM-PNSEC-1` | FEU | NCR | 3,963 | Taglish 38%, Filipino 32%, English 26% | 2024-05 → 2026-02 | **7** | 0.5% | -0.002 | 0.203 | 0% | 29% | 0 |
| `MM-PSEC-1` | ADMU | NCR | 3,735 | English 76%, Taglish 13%, Filipino 6% | 2025-11 → 2026-05 | **44** | 33.5% | -0.022 | 0.414 | 0% | 0% | 0 |
| `MM-PUB-1` | UPD | NCR | 3,578 | Filipino 36%, Taglish 29%, English 28% | 2024-06 → 2026-04 | **5** | 0.0% | 0.155 | 0.387 | 0% | 0% | 0 |

## Aggregate statistics

| Metric | Min | Median | Max |
|---|---|---|---|
| Topics per university | 5 | 7 | 44 |
| Outlier rate | 0.0% | 0.5% | 33.5% |
| NPMI | -0.022 | -0.002 | 0.155 |

## Universities not yet complete

- `CAR-PNSEC-1` (UB) — 3,991 posts in FW-09_cleaned.json
- `CAR-PNSEC-2` (LPU-B) — 3,912 posts in FW-05_cleaned.json
- `CAR-PSEC-1` (SLU) — 3,864 posts in SLU_cleaned.json
- `CAR-PUB-1` (UPB) — 2,287 posts in FW-07_cleaned.json
- `CAR-PUB-2` (BSU) — 3,791 posts in FW-08_cleaned.json
- `MIN-PUB-1` (CSU) — 3,998 posts in FW-06_cleaned.json
- `PROV-PUB-1` (UPLB) — 3,955 posts in FW-04_cleaned.json

## How to read topic-count variation

Cross-university topic-count differences are a **finding**, not a methodological flaw. Each university's Freedom Wall has its own linguistic mix, time window, and posting culture, which produce genuinely different density structures in the embedding space. The pipeline's `target_topic_count` is a *ceiling* (via reduce_topics) rather than a target — universities with naturally clean structure (few well-separated themes) keep their natural count; universities with over-fragmented structure get merged down to the target.

For fair cross-university comparison prefer **outlier_rate** (discourse cohesion), **NPMI** (within-topic coherence), and **event_driven %** (temporal concentration). Raw topic count alone should be interpreted alongside these metrics in the thesis discussion.
