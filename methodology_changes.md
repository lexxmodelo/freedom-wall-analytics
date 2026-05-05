# Methodology Changes: From Proposal to Execution

**Document Type:** Applied Revision Record  
**Base Document:** Research.md (Thesis Proposal, December 14, 2025)  
**Revision Date:** May 1, 2026  
**Status:** Pre-Execution Audit — All Changes Pending Implementation

---

## 1. Executive Summary

This document records every methodological modification applied to the original thesis proposal before execution begins. Three categories of change are enforced: (1) infrastructure migration from local GPU inference to cloud API, (2) data governance tightening, and (3) institutional de-identification. Each change carries downstream consequences for the pipeline, the validation strategy, and the ethical framework. All trade-offs are documented explicitly.

The resulting system is a **hybrid architecture**: local compute for preprocessing, embedding, and clustering; cloud API (NVIDIA NIM) for generative inference (topic labeling + VAD scoring). This separation preserves the proposal's core methodology while resolving its most critical bottleneck — the RTX 4050's inability to run Llama-3-8B at production throughput for 120,000+ posts.

---

## 2. Change Registry

### 2.1 LLM Replacement: Local Llama-3-8B → NVIDIA NIM Llama 3.3 70B Instruct

| Attribute | Original | Revised |
|---|---|---|
| Model | Llama-3-8B-Instruct (4-bit quantized) | Llama 3.3 70B Instruct (full precision, cloud-hosted) |
| Model ID | N/A (local binary) | `meta/llama-3.3-70b-instruct` |
| Inference Location | Local (RTX 4050, 6GB VRAM) | NVIDIA NIM Cloud API (`integrate.api.nvidia.com/v1`) |
| API Format | llama-cpp-python / Ollama (local socket) | OpenAI-compatible chat completions (HTTPS) |
| Context Window | ~4K tokens (4-bit quantized limit) | 128K tokens |
| Rate Limit | Bounded by GPU throughput (~2-5 tok/s) | 40 requests/minute (free tier) |
| Temperature | 0.1 (locked) | 0.1 (locked, preserved) |

**Justification:**

The original proposal's RTX 4050 (6GB VRAM) cannot run Llama-3-8B-Instruct at 4-bit quantization with acceptable throughput for 120,000 posts. At ~2-5 tokens/second for generation, a single VAD scoring pass would take approximately 15-20 days of continuous inference. This is operationally infeasible. The 70B model via NIM also provides substantially better multilingual reasoning, more reliable JSON schema adherence, and stronger chain-of-thought capability for sarcasm detection — all critical weaknesses of the 8B variant on Taglish text.

**Impact on BERTopic Integration:**

The original design embedded the LLM inside BERTopic via `bertopic.representation.TextGeneration`, which expects a local HuggingFace pipeline or llama-cpp model. This integration path is incompatible with an external API.

**Resolution:** Decouple topic labeling from BERTopic. Run BERTopic for clustering and c-TF-IDF extraction only. Topic labeling becomes a separate post-clustering step that calls the NIM API with the same inputs (top-10 keywords + top-5 representative documents). This decoupling is architecturally cleaner: it separates the unsupervised learning stage from the generative interpretation stage, and it allows independent retry/validation of labels without re-running the entire clustering pipeline.

```
ORIGINAL:  BERTopic(representation_model=TextGeneration(local_llm)) → labels inline
REVISED:   BERTopic(representation_model=None) → clusters + c-TF-IDF → NIM API → labels
```

**Impact on Sentiment Analysis:**

No structural change. The VAD scoring prompt is model-agnostic. The 70B model's improved instruction-following means:
- JSON schema compliance will be higher (fewer malformed outputs)
- Chain-of-thought sarcasm detection will be more reliable
- Few-shot anchoring for rare emotions will generalize better
- The "Unknown" / "Incoherent" misclassification rate from the pilot should drop significantly

---

### 2.2 Rate Limiting and Throughput Strategy

**Constraint:** 40 requests/minute (NVIDIA NIM free tier, non-negotiable without enterprise agreement).

**Throughput Budget:**

| Task | Request Count | Batching | Effective Requests | Time at 40 RPM |
|---|---|---|---|---|
| Topic Labeling | ~50-100 topics × 12 universities | 1 topic per request | ~600-1,200 | 15-30 min |
| VAD Scoring | ~120,000 posts | 5 posts per request | ~24,000 | 10 hours |
| Sarcasm Re-evaluation | ~5% flagged posts | 5 posts per request | ~1,200 | 30 min |
| **Total** | | | **~26,400** | **~11 hours** |

**Batching Design for VAD Scoring:**

Each API request contains 5 posts bundled with their assigned topic labels. The prompt instructs the model to return a JSON array of 5 VAD objects. Batch size of 5 (not 10) was chosen to:
- Keep input under ~3,000 tokens per request (well within 128K)
- Reduce the risk of the model confusing posts within a batch
- Allow granular retry if a single post causes a malformed response

```json
// Expected response format per batch
[
  {"post_id": "abc123", "V": 3, "A": 7, "D": 2, "sarcasm": false},
  {"post_id": "def456", "V": 6, "A": 4, "D": 7, "sarcasm": false},
  ...
]
```

**Rate Limiter Implementation:**

```
Strategy: Token bucket algorithm (40 tokens, refill 40/min)
Library:  asyncio.Semaphore + time-based refill
Backoff:  Exponential (1s, 2s, 4s, 8s, 16s) on HTTP 429
Max retries: 5 per request
Timeout:  30 seconds per request
Circuit breaker: After 10 consecutive failures, pause 5 minutes and alert
```

**Checkpoint/Resume System:**

Long-running inference jobs (10+ hours) cannot assume uninterrupted execution. The pipeline writes a checkpoint file after every 100 successful requests:

```json
{
  "task": "vad_scoring",
  "university": "MM-PUB-1",
  "last_completed_batch": 1542,
  "total_batches": 4800,
  "timestamp": "2026-05-01T14:30:00+08:00",
  "failed_post_ids": ["abc123", "xyz789"]
}
```

On restart, the pipeline reads the checkpoint and resumes from `last_completed_batch + 1`. Failed posts are collected and retried in a separate pass.

---

### 2.3 Data Source Constraints

| Constraint | Original | Revised |
|---|---|---|
| Source | Facebook Freedom Wall Pages (public + ambiguous) | Facebook Freedom Wall Pages (verified public only) |
| Scraper | Apify Facebook Page Scraper | Apify Facebook Page Scraper with public-access verification |
| Login | Not explicitly addressed | **Prohibited** — scraper must operate without authentication tokens |
| Private Groups | Excluded by stated scope | Excluded with automated detection (reject any source requiring group membership) |
| Comment Sections | Excluded | Excluded (unchanged) |
| Multimedia | Excluded | Excluded (unchanged) |

**Critical Issue Identified:**

Many Apify Facebook scrapers require a Facebook session cookie or login token to access page content. If the scraper authenticates as a user to access "public" pages, this violates the public-data-only constraint — the data is being accessed through an authenticated session, which means the scraper has access to content that may not be visible to a logged-out user.

**Resolution:**

1. Verify that the Apify actor operates in **unauthenticated mode** (no cookies, no login tokens)
2. For each target Freedom Wall page, manually confirm public visibility by accessing the page in an incognito browser with no Facebook account
3. Document the public accessibility status of each page at the time of scraping
4. If a page requires login to view posts, it is excluded from the dataset entirely
5. Record the Apify actor version, configuration, and run parameters for reproducibility

**Fallback:** If Facebook's anti-scraping measures block unauthenticated access to all target pages, the study must pivot to an alternative public data source or explicitly acknowledge the authenticated access in the ethics section with justification under legitimate academic interest provisions of the Philippine Data Privacy Act.

---

### 2.4 Institutional Anonymization

All specific university names are replaced with cluster-based codes. The codename scheme preserves the three analytical dimensions from the original proposal: geographic cluster, institutional type, and ordinal index.

**Codename Format:** `{CLUSTER}-{TYPE}-{INDEX}`

| Cluster Code | Geographic Region |
|---|---|
| MM | Metro Manila |
| PROV | Luzon Provincial |
| CAR | Cordillera Administrative Region (Baguio/Benguet) |

| Type Code | Institutional Category |
|---|---|
| PUB | State University / Public HEI |
| PSEC | Private Sectarian |
| PNSEC | Private Non-Sectarian |

**Mapping (12 institutions):**

| Original (REMOVED from all outputs) | Anonymized Code |
|---|---|
| [Metro Manila State University 1] | MM-PUB-1 |
| [Metro Manila State University 2] | MM-PUB-2 |
| [Metro Manila Private Sectarian 1] | MM-PSEC-1 |
| [Metro Manila Private Sectarian 2] | MM-PSEC-2 |
| [Metro Manila Private Non-Sectarian 1] | MM-PNSEC-1 |
| [Provincial State University 1] | PROV-PUB-1 |
| [Provincial State University 2] | PROV-PUB-2 |
| [Provincial Private Non-Sectarian 1] | PROV-PNSEC-1 |
| [CAR State University 1] | CAR-PUB-1 |
| [CAR State University 2] | CAR-PUB-2 |
| [CAR Private Non-Sectarian 1] | CAR-PNSEC-1 |
| [Pilot Study Institution — baseline] | CAR-PSEC-1 |

**Cross-Reference Prevention:**

Anonymization is only meaningful if the reader cannot reverse-engineer the mapping. The following measures apply:

1. **Department acronyms stripped:** The University-Specific Dictionary Mapping (Section 3.3.6) originally used department codes like 'SAMCIS', 'CSSP', 'GCOE' which uniquely identify institutions. These are replaced with generic codes: `DEPT-ENG`, `DEPT-BUS`, `DEPT-SCI`, `DEPT-ART`, etc.
2. **Freedom Wall page names redacted:** Any page name or URL that identifies the institution is removed from all datasets and outputs.
3. **Enrollment size ranges:** If the paper reports institutional statistics (post volume, student body size), these are reported as ranges (e.g., "10,000-20,000 enrolled students") rather than exact figures.
4. **Geographic specificity limited:** Posts mentioning campus-specific landmarks (e.g., specific building names, local street names) have those entities masked with `[CAMPUS_LOCATION]` during preprocessing.

**Trade-off:** This anonymization reduces the paper's practical utility for administrators at specific institutions who might want to benchmark their Freedom Wall against peers. However, it is necessary for ethical publication and prevents reputational harm to any single institution based on the sentiment findings.

---

## 3. Pipeline Adjustments

### 3.1 Updated Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                        DATA COLLECTION LAYER                        │
│  Apify (unauthenticated) → Raw JSON → Public Access Verification   │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     PREPROCESSING LAYER (LOCAL)                     │
│  Field Selection → Normalization → Regex Cleaning →                 │
│  Linguistic Preservation → Stopword Removal →                       │
│  Anonymization (NER + Regex) → Institution Codename Mapping →       │
│  Campus Landmark Masking → Output Serialization (UTF-8 JSON)        │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    EMBEDDING + CLUSTERING (LOCAL)                    │
│  paraphrase-multilingual-MiniLM-L12-v2 (CPU) →                     │
│  UMAP (15 neighbors, 5 components, cosine, mindist=0.05) →         │
│  HDBSCAN (grid search: min_cluster 30-100) →                        │
│  c-TF-IDF (custom Taglish stopwords) →                              │
│  Soft-clustering reassignment (threshold ≥ 0.50) →                  │
│  Per-university topic models                                        │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
          ┌─────────────────────┴─────────────────────┐
          │                                           │
          ▼                                           ▼
┌─────────────────────────┐             ┌─────────────────────────────┐
│  TOPIC LABELING (API)   │             │   VAD SCORING (API)         │
│  NIM: Llama 3.3 70B     │             │   NIM: Llama 3.3 70B       │
│  Input: top-10 kw +     │             │   Input: post + topic +    │
│    top-5 rep docs        │             │     few-shot examples       │
│  Output: 5-word label   │             │   Output: {V,A,D,sarcasm}  │
│  Constraint: temp=0.1   │             │   Batch: 5 posts/request   │
│  Rate: 40 RPM           │             │   CoT: sarcasm pre-check   │
│  ~600-1200 requests     │             │   Rate: 40 RPM             │
└────────────┬────────────┘             │   ~24,000 requests         │
             │                          └──────────────┬──────────────┘
             │                                         │
             └────────────────┬────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   POST-PROCESSING + VALIDATION                      │
│  Label deduplication → Lazy-label detection → VAD range check →     │
│  Schema validation → Checkpoint merge →                             │
│  HITL sample extraction (5% stratified) → Label Studio export       │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     DASHBOARD + OUTPUT (LOCAL)                      │
│  Flask + Chart.js → Global Overview + Topic Drill-Down +            │
│  Temporal Analysis → JSON flat-file store                           │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 Preprocessing Changes

Two new stages are added to the preprocessing pipeline:

**Stage 3.3.6a — Campus Landmark Masking:**

After the existing NER pipeline masks person names, a secondary pass identifies and masks campus-specific geographic references that could de-anonymize institutions. A curated dictionary per institution maps known landmarks, building names, and local street names to the generic token `[CAMPUS_LOCATION]`. This step runs after NER and before academic unit categorization.

**Stage 3.3.6b — Institution Code Injection:**

Replace the original University-Specific Dictionary Mapping with the anonymized codename scheme. The configuration file maps each institution's original identifiers to its code (e.g., all references to a specific institution's departments become `{CODE}-DEPT-*`). This mapping file is stored separately from the published dataset and is not included in any public release.

### 3.3 Topic Labeling Pipeline (Revised)

**Original Flow:** BERTopic → TextGeneration(local_llm) → inline labels  
**Revised Flow:** BERTopic → extract keywords + rep docs → NIM API → labels → merge back

The labeling prompt is preserved with minor adjustments for the 70B model's capabilities:

```
SYSTEM: You are an expert Data Analyst for Philippine universities. You analyze
Taglish (Tagalog-English) social media posts from anonymous student feedback
platforms.

USER: Analyze the following topic cluster.

Keywords: [KEYWORDS]

Representative posts:
[DOCUMENTS]

Generate a single label that is:
- Specific to the content (not generic)
- Maximum 5 words
- Professional and descriptive
- In English

If the posts are incoherent, spam, or lack a unifying theme, output exactly: Noise

Output ONLY the label. No explanation, no punctuation, no quotes.
```

**Changes from original:**
1. System/User role separation (leveraging chat completions format)
2. Explicit "In English" instruction (70B model may default to Taglish labels otherwise)
3. Stricter "Noise" fallback criteria
4. "No quotes" added — the 70B model tends to wrap outputs in quotation marks

### 3.4 VAD Scoring Pipeline (Revised)

**Batch prompt structure for 5 posts:**

```
SYSTEM: You are a psycholinguistic analyst specializing in Filipino student
discourse. You score social media posts on the Self-Assessment Manikin (SAM)
scale across three dimensions:

- Valence (V): 1 = extremely negative, 9 = extremely positive
- Arousal (A): 1 = calm/passive, 9 = excited/agitated
- Dominance (D): 1 = helpless/controlled, 9 = empowered/in-control

You also detect sarcasm and irony in Taglish text.

USER: Score the following 5 posts. Each post has an ID and an assigned topic for
context.

[Few-shot examples: 3 anchoring examples covering low-V/low-A (burnout),
high-A/low-D (rage), and sarcastic praise]

Post 1 [ID: {id}] (Topic: {topic}): "{text}"
Post 2 [ID: {id}] (Topic: {topic}): "{text}"
Post 3 [ID: {id}] (Topic: {topic}): "{text}"
Post 4 [ID: {id}] (Topic: {topic}): "{text}"
Post 5 [ID: {id}] (Topic: {topic}): "{text}"

IMPORTANT: Before scoring, internally assess whether each post uses sarcasm,
irony, or exaggeration. If sarcasm is detected, score based on the TRUE
underlying emotion, not the surface text.

Respond with ONLY a JSON array of 5 objects:
[{"id":"...","V":int,"A":int,"D":int,"sarcasm":bool}, ...]
```

**Changes from original:**
1. Batch processing (5 posts per request instead of 1)
2. Post IDs included for response-to-post mapping
3. Topic context included in the prompt (unchanged in intent, explicit in implementation)
4. Sarcasm detection integrated into the scoring prompt rather than as a separate CoT step — the 70B model handles this in a single pass, reducing request count
5. Few-shot examples are now hardcoded in the prompt template (3 examples) rather than dynamically selected — the 70B model's larger context window makes this feasible without crowding

---

## 4. New Constraints

### 4.1 Privacy Constraints from Cloud API

**Critical Change:** The original proposal's data security model was built on air-gapped local processing. Moving to NVIDIA NIM introduces a new data flow where anonymized post text is transmitted to NVIDIA's servers.

**NVIDIA NIM Free Tier ToU (Section 6):** Grants NVIDIA rights to use "User Content" to "modify and improve NVIDIA products or services." This language is ambiguous and could permit using submitted text for model training.

**Mitigations:**

1. **Pre-API anonymization is mandatory.** The NER + regex anonymization pipeline MUST run before any text is sent to the API. No post text reaches the API with person names, student numbers, email addresses, or institution-identifying information.
2. **Campus landmark masking** (new stage) ensures that geographic references that could identify institutions are masked before API submission.
3. **The ethics section must disclose** that anonymized text is processed by a third-party cloud service (NVIDIA), with a reference to NVIDIA's Terms of Use and Data Processing Addendum.
4. **If IRB or ethics board objects:** Fall back to self-hosted NIM (requires NVIDIA AI Enterprise license at ~$1/GPU/hour on cloud GPU, or $4,500/GPU/year for on-premise). This eliminates the data transmission concern entirely but introduces cost.
5. **Data retention:** No post-inference data is stored on the API side by design (stateless API calls). However, NVIDIA's internal logging practices are not transparent for free-tier users. Document this limitation.

### 4.2 Reproducibility Constraints

Moving from a local model binary to a cloud API introduces version drift risk. The 70B model served by NIM may be updated without notice. To ensure reproducibility:

1. Record the exact model ID, API endpoint, and response headers (including any model version identifiers) for every inference run
2. Cache all API responses locally with their prompts — this creates a complete record that can be audited without re-running inference
3. If NVIDIA changes the model version mid-experiment, document the change and report results separately for each model version

### 4.3 Cost Constraints

At the free tier (40 RPM, no per-token billing), the pipeline is cost-free but time-constrained. If the free tier is revoked or rate-limited further:

- **Fallback 1:** OpenRouter provides Llama 3.3 70B at ~$0.04/M input tokens. Total pipeline cost at ~50M input tokens: ~$2.00
- **Fallback 2:** Together.ai provides the same model at comparable pricing with higher rate limits
- **Fallback 3:** Self-hosted via NVIDIA AI Enterprise on a cloud A100 instance (~$1-3/hour, ~11 hours = $11-33)

---

## 5. Trade-offs

| Trade-off | Gained | Lost | Severity |
|---|---|---|---|
| Cloud API vs local GPU | 10x model capability, feasible throughput | Air-gapped data security, deterministic versioning | Medium — mitigated by pre-API anonymization |
| Decoupled topic labeling | Independent retry, cleaner architecture | Inline BERTopic integration (simpler code) | Low — net positive |
| Batch VAD scoring (5/request) | 5x throughput improvement | Per-post CoT reasoning visibility | Low — aggregated CoT is sufficient |
| Institution anonymization | Publication ethics, harm prevention | Direct actionability for specific institutions | Medium — acceptable for academic publication |
| Unauthenticated scraping only | Clean ethical posture | Possible loss of target pages that require login | High — may require scope reduction |
| 40 RPM rate limit | Zero cost | 11-hour inference window per full run | Medium — acceptable for batch processing |

---

## 6. Risk Registry

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| NVIDIA NIM free tier discontinued | Medium | High | Fallback to OpenRouter / Together.ai / self-hosted |
| Facebook blocks unauthenticated scraping for all target pages | Medium | Critical | Pivot to authenticated scraping with ethics board disclosure, or reduce scope |
| 70B model produces different label style than 8B pilot | High | Low | Re-calibrate lazy-label detection thresholds; human validation catches drift |
| API responses contain malformed JSON | Medium | Low | JSON repair library (e.g., `json_repair`) + schema validation + retry |
| Rate limit exceeded despite token bucket | Low | Low | Exponential backoff + circuit breaker handles this automatically |
| Anonymization leaks through context | Low | Medium | Multi-layer masking (NER + landmarks + department codes) + manual spot-check |
| NVIDIA logs/retains anonymized post text | Medium | Medium | Pre-API anonymization ensures no PII; disclose in ethics section |
| Model version changes mid-experiment | Medium | Medium | Cache all responses; report model version in results |
| Apify actor version breaks between scraping runs | Medium | High | Pin actor version; complete all scraping in a single batch window |

---

## 7. Justification Matrix

Every change maps to one of three drivers: **Feasibility** (the original design cannot execute), **Ethics** (the original design has a governance gap), or **Quality** (the change improves the output).

| Change | Driver | Original Flaw |
|---|---|---|
| Llama-3-8B → Llama 3.3 70B via NIM | Feasibility | RTX 4050 cannot process 120K posts in any reasonable timeframe |
| Decoupled topic labeling | Feasibility | TextGeneration module incompatible with external API |
| Batch VAD scoring | Feasibility | 120K individual API calls at 40 RPM = 50 hours; batching reduces to 10 hours |
| Rate limiter + retry logic | Feasibility | Original had no failure handling (local inference assumed reliable) |
| Checkpoint/resume system | Feasibility | 11-hour jobs cannot assume uninterrupted execution |
| Unauthenticated scraping enforcement | Ethics | Original did not verify scraper authentication status |
| Pre-API anonymization mandate | Ethics | Cloud transmission was not part of original threat model |
| Institution anonymization | Ethics | Named institutions could suffer reputational harm from sentiment findings |
| Campus landmark masking | Ethics | Geographic references could de-anonymize institutions |
| 70B model for sarcasm detection | Quality | 8B model had high "Unknown" rate on sarcastic Taglish posts |
| Few-shot anchoring in VAD prompt | Quality | Original mentioned few-shot but did not specify implementation |
| Response caching for reproducibility | Quality | Cloud API introduces version drift risk absent from local inference |

---

## 8. Distributed Workload Strategy (Multiple API Keys)

### 8.1 Rationale

To reduce the total inference time for topic labeling and VAD scoring, the workload is distributed across multiple researchers, each using their own NVIDIA NIM API key on their own computer. This is **not** rate-limit circumvention — each researcher uses a single key on a single machine, processing a distinct, non-overlapping subset of the data. This is functionally equivalent to one researcher running jobs sequentially, but with parallelization across hardware.

### 8.2 Assignment Strategy

| Researcher | API Key | Assigned Universities | Est. Posts | Est. Time |
|---|---|---|---|---|
| Researcher 1 | `nvapi-...` | MM-PUB-1, MM-PUB-2, MM-PSEC-1 | ~30,000 | ~2.5 hrs |
| Researcher 2 | `nvapi-...` | MM-PSEC-2, MM-PNSEC-1, PROV-PUB-1 | ~30,000 | ~2.5 hrs |
| Researcher 3 | `nvapi-...` | PROV-PUB-2, PROV-PNSEC-1, CAR-PUB-1 | ~30,000 | ~2.5 hrs |
| Researcher 4 | `nvapi-...` | CAR-PUB-2, CAR-PNSEC-1, CAR-PSEC-1 | ~30,000 | ~2.5 hrs |

**Total Pipeline Time:** ~2.5 hours (down from ~11 hours single-machine)

### 8.3 Per-Researcher Configuration

Each researcher receives a JSON config file:

```json
{
  "researcher_id": "researcher_1",
  "api_key_env_var": "NVIDIA_NIM_API_KEY",
  "assigned_universities": ["MM-PUB-1", "MM-PUB-2", "MM-PSEC-1"],
  "checkpoint_dir": "./checkpoints/researcher_1/",
  "output_dir": "./results/researcher_1/",
  "rate_limit_rpm": 40,
  "batch_size": 5,
  "temperature": 0.1,
  "model_id": "meta/llama-3.3-70b-instruct"
}
```

### 8.4 Coordination Protocol

1. **Dataset Splitting:** The cleaned dataset is split by university before distribution. Each researcher receives only their assigned universities' posts.
2. **No Overlap:** No post is assigned to more than one researcher. Topic models (BERTopic) are trained **per-university**, so each researcher trains their own BERTopic model for their assigned institutions.
3. **Common Seed:** All BERTopic hyperparameters (UMAP neighbors, HDBSCAN min_cluster, embedding model) are documented and shared to ensure comparability across researchers.
4. **Post-Merge:** After all researchers complete their runs, a merge script combines:
   - All topic labels into a unified taxonomy
   - All VAD scores into a single dataset
   - All checkpoints for audit trail

### 8.5 Validation Across Researchers

To ensure consistency across distributed workers:

1. **Inter-Rater Reliability (Pilot):** Before full-scale execution, all researchers score the same 100-post sample. ICC (Intraclass Correlation Coefficient) must be ≥ 0.75 for VAD scores. If below threshold, recalibrate prompts or reduce temperature.
2. **Label Harmonization:** After topic labeling, run a deduplication pass. If two researchers produce semantically identical labels with different wording (e.g., "Academic Stress" vs "School Pressure"), map them to a canonical label.
3. **Schema Compliance:** All outputs must pass identical JSON schema validation before merge.

### 8.6 Risks of Distributed Execution

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Researchers use different prompt versions | Medium | High | Version-controlled prompt template in Git; script reads from shared file |
| Researchers start at different times, model version drift | Medium | Medium | Record model version in every API response; reject mismatched versions |
| One researcher hits rate limit harder due to time-of-day | Low | Low | Each researcher has independent 40 RPM quota; no cross-researcher contention |
| Data files get mixed up during merge | Low | High | Strict directory structure; merge script validates researcher_id in every record |
| API key revoked for one researcher | Low | High | Fallback to OpenRouter/Together.ai for that researcher; do not redistribute keys |
