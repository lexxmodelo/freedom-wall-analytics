# Cross-University Topic Modeling Summary

_Generated 2026-05-06 08:09 UTC_

Universities completed: **10** of 10

## Completed universities

| Code | Region | Posts | Top languages | Date range | Topics | Outlier % | NPMI | Silhouette | Lazy labels % | Event-driven % | API fails |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `CAR-PNSEC-1` | CAR | 3,991 | Filipino 47%, Taglish 38%, English 12% | 2024-06 → 2026-03 | **7** | 1.6% | 0.072 | 0.426 | 0% | 57% | 0 |
| `PROV-PNSEC-1` | CALABARZON | 3,912 | Filipino 56%, Taglish 27%, English 11% | 2025-08 → 2025-12 | **29** | 44.0% | -0.118 | 0.492 | 0% | 0% | 3 |
| `CAR-PSEC-1` | CAR | 3,864 | Filipino 39%, Taglish 38%, English 18% | 2025-04 → 2026-05 | **9** | 3.9% | 0.044 | 0.289 | 0% | 33% | 0 |
| `CAR-PUB-1` | CAR | 2,287 | Filipino 40%, Taglish 34%, English 20% | 2025-06 → 2026-04 | **6** | 0.5% | 0.104 | 0.234 | 0% | 17% | 0 |
| `CAR-PUB-2` | CAR | 3,791 | Filipino 42%, Taglish 36%, English 15% | 2025-11 → 2026-05 | **6** | 0.2% | -0.018 | 0.241 | 0% | 17% | 0 |
| `MIN-PUB-1` | CARAGA | 3,998 | Cebuano 27%, Taglish 27%, English 25% | 2026-01 → 2026-05 | **29** | 42.2% | -0.014 | 0.444 | 0% | 24% | 8 |
| `MM-PNSEC-1` | NCR | 3,963 | Taglish 38%, Filipino 32%, English 26% | 2024-05 → 2026-02 | **7** | 0.5% | -0.002 | 0.203 | 0% | 29% | 0 |
| `MM-PSEC-1` | NCR | 3,735 | English 76%, Taglish 13%, Filipino 6% | 2025-11 → 2026-05 | **44** | 33.5% | -0.022 | 0.414 | 0% | 0% | 14 |
| `MM-PUB-1` | NCR | 3,578 | Filipino 36%, Taglish 29%, English 28% | 2024-06 → 2026-04 | **5** | 0.0% | 0.155 | 0.387 | 0% | 0% | 0 |
| `PROV-PUB-1` | CALABARZON | 3,955 | Filipino 38%, Taglish 36%, English 22% | 2025-12 → 2026-04 | **5** | 0.2% | 0.042 | -0.076 | 0% | 0% | 0 |

## Aggregate statistics

| Metric | Min | Median | Max |
|---|---|---|---|
| Topics per university | 5 | 7 | 44 |
| Outlier rate | 0.0% | 1.6% | 44.0% |
| NPMI | -0.118 | 0.042 | 0.155 |

## How to read topic-count variation

Cross-university topic-count differences are a **finding**, not a methodological flaw. Each university's Freedom Wall has its own linguistic mix, time window, and posting culture, which produce genuinely different density structures in the embedding space. The pipeline's `target_topic_count` is a *ceiling* (via reduce_topics) rather than a target — universities with naturally clean structure (few well-separated themes) keep their natural count; universities with over-fragmented structure get merged down to the target.

For fair cross-university comparison prefer **outlier_rate** (discourse cohesion), **NPMI** (within-topic coherence), and **event_driven %** (temporal concentration). Raw topic count alone should be interpreted alongside these metrics in the thesis discussion.
