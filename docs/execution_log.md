# Execution Log: Pre-Implementation Audit

**Document Type:** Research Lab Notebook + Engineering Decision Record  
**Base Document:** Research.md (Thesis Proposal, December 14, 2025)  
**Audit Date:** May 1, 2026  
**Auditor Role:** Senior Research Engineer / AI Systems Architect  
**Scope:** Full pipeline review — data collection through dashboard delivery

---

## 1. Analysis Session Record

### 1.1 Document Intake

Read the full 1,587-line proposal end-to-end. The document is a thesis proposal for an AI-driven system that performs topic modeling (BERTopic) and multidimensional sentiment analysis (VAD via LLM) on anonymized Facebook Freedom Wall posts from 12 Philippine universities. The proposal is well-structured and demonstrates genuine understanding of the NLP landscape. The pilot study results (BERTopic coherence 0.58 vs LDA 0.34 on 20K SLU posts) provide real empirical grounding.

### 1.2 Pipeline Extraction

The core pipeline has 9 stages:

```
1. Data Collection (Apify → raw JSON)
2. Preprocessing (7 sub-stages)
3. Embedding (paraphrase-multilingual-MiniLM-L12-v2 or RoBERTa-Tagalog)
4. Dimensionality Reduction (UMAP)
5. Clustering (HDBSCAN)
6. Topic Representation (c-TF-IDF + LLM labeling)
7. Sentiment Analysis (LLM-based VAD scoring)
8. Human Validation (Label Studio + 8 annotators)
9. Dashboard (Flask + Chart.js)
```

### 1.3 Dependency Inventory

| Component | Dependency | Version Risk | Replacement Risk |
|---|---|---|---|
| Scraper | Apify Facebook Page Scraper | High (Facebook changes DOM frequently) | Medium (alternative scrapers exist) |
| Embedding | paraphrase-multilingual-MiniLM-L12-v2 | Low (stable SentenceTransformers model) | Low |
| Embedding (alt) | RoBERTa-Tagalog | Low | Low |
| Clustering | BERTopic + HDBSCAN + UMAP | Low (mature libraries) | Low |
| LLM (labeling) | Llama-3-8B-Instruct (local) | **Critical — replaced** | N/A |
| LLM (VAD) | Llama-3-8B-Instruct (local) | **Critical — replaced** | N/A |
| NER | spaCy or Microsoft Presidio | Low | Low |
| Annotation | Label Studio | Low | Low |
| Dashboard | Flask + Chart.js | Low | Low |
| GPU | NVIDIA RTX 4050 (6GB VRAM) | **Critical — insufficient** | Mitigated by API migration |

### 1.4 Data Flow Verification

Traced the data flow from raw scrape to dashboard output. Found two undocumented data transformations:

1. **Engagement metrics flow dead-ends.** Likes, shares, and comments are collected (Section 3.3.1) and normalized (Section 3.3.2), but there is no downstream stage that uses them. The proposal mentions "linking high-engagement posts with specific high-arousal topics" but does not specify how. This is a dangling data path.

2. **RoBERTa-Tagalog role is ambiguous.** Section 3.4 describes it as a "control group" for embeddings, but no experimental design compares its performance against the primary model. This suggests it was part of the pilot but was not formalized into the proposal methodology.

---

## 2. Flaw Registry

### FLAW-001: GPU Throughput Infeasibility (CRITICAL)

**Location:** Sections 3.5.1, 3.6.1  
**Description:** The RTX 4050 has 6GB VRAM. Running Llama-3-8B-Instruct at 4-bit quantization requires ~4.5GB VRAM for weights alone, leaving ~1.5GB for KV cache. At batch size 1, this yields approximately 2-5 tokens/second for generation. For 120,000 posts requiring both topic labeling and VAD scoring, the total inference time exceeds 15 days of continuous processing.  
**Severity:** Critical — the system as designed cannot execute within any reasonable research timeline.  
**Fix:** Migrate to NVIDIA NIM API (Llama 3.3 70B Instruct). See methodology_changes.md Section 2.1.

### FLAW-002: Scraper Authentication Status Unverified (HIGH)

**Location:** Section 3.2  
**Description:** The proposal states data is "publicly available" but does not verify whether the Apify actor requires Facebook authentication to access page content. Many Apify Facebook scrapers inject session cookies. If the scraper authenticates as a Facebook user, the "public data" claim is technically false — the scraper is accessing content through an authenticated session that may reveal content not visible to logged-out users.  
**Severity:** High — undermines the ethical foundation of the data collection strategy.  
**Fix:** Enforce unauthenticated scraping. Verify each target page is accessible without login. See methodology_changes.md Section 2.3.

### FLAW-003: BERTopic-LLM Integration Incompatible with API (HIGH)

**Location:** Section 3.5.1  
**Description:** The `bertopic.representation.TextGeneration` module expects a local HuggingFace pipeline or llama-cpp model object. It cannot make HTTP API calls to an external service. The proposal assumes this integration "just works," but the code path requires a callable model object in memory.  
**Severity:** High — the labeling pipeline will fail at runtime if the API migration is applied without decoupling.  
**Fix:** Decouple topic labeling from BERTopic. Run clustering first, then label topics via separate API calls. See methodology_changes.md Section 2.1.

### FLAW-004: No Failure Handling for LLM Inference (HIGH)

**Location:** Sections 3.5, 3.6  
**Description:** The original design assumes local inference is reliable (no network failures, no timeouts, no rate limits). There is no retry logic, no checkpoint system, and no strategy for partial failures. Even with local inference, GPU OOM errors, driver crashes, or power interruptions could corrupt a multi-day run with no recovery mechanism.  
**Severity:** High — any interruption requires restarting the entire inference pipeline from scratch.  
**Fix:** Implement rate limiter, exponential backoff retry, checkpoint/resume system, and circuit breaker. See methodology_changes.md Section 2.2.

### FLAW-005: Engagement Metrics Data Path Dead-Ends (MEDIUM)

**Location:** Sections 3.3.1, 3.3.2  
**Description:** The proposal collects and normalizes engagement metrics (likes, shares, comments) but never uses them in any analytical stage. Section 3.3.2 mentions "linking high-engagement posts with specific high-arousal topics" but this is aspirational — no method section implements it. The data is collected, cleaned, and then ignored.  
**Severity:** Medium — wasted preprocessing effort, and reviewers will question why the data was collected if not used.  
**Fix:** Either (a) define a specific analysis stage that correlates engagement metrics with VAD scores and topic assignments, or (b) remove engagement collection from the preprocessing pipeline and acknowledge it as out-of-scope. Option (a) is recommended — engagement as a proxy for post salience is a defensible analytical addition.

**Recommended Implementation:** Add engagement as a weighting factor in the dashboard's temporal analysis module. High-engagement posts receive visual emphasis. Optionally, report Spearman rank correlations between engagement and arousal scores to test whether "viral" posts tend to be higher-arousal.

### FLAW-006: RoBERTa-Tagalog Role Undefined (MEDIUM)

**Location:** Section 3.4  
**Description:** RoBERTa-Tagalog is described as a "control group" for embeddings, but no experimental design compares its output against the primary model (paraphrase-multilingual-MiniLM-L12-v2). A control group requires (a) running the same clustering pipeline on both embedding sets, (b) comparing coherence scores, silhouette scores, and topic stability, and (c) reporting the comparison. The proposal does not include any of these steps.  
**Severity:** Medium — the term "control group" implies experimental rigor that is not delivered.  
**Fix:** Choose one of two paths:

- **Path A (Ablation Study):** Run the full BERTopic pipeline with both embedding models on the same dataset. Report coherence, silhouette, and stability metrics for each. This turns the comparison into a proper ablation study and strengthens the paper's contribution.
- **Path B (Remove):** Drop RoBERTa-Tagalog from the methodology and use only paraphrase-multilingual-MiniLM-L12-v2. Acknowledge in the limitations that alternative embedding models were not systematically evaluated.

**Recommendation:** Path A is strongly preferred for a publication. It adds a methodological contribution and only requires running the embedding + clustering stages twice (no additional LLM inference needed).

### FLAW-007: VAD Score Validation Strategy Insufficient (MEDIUM)

**Location:** Section 3.7  
**Description:** The HITL validation strategy uses Cohen's Kappa for topic labels (categorical) and ICC for VAD scores (continuous). However, VAD scores are generated by an LLM with no ground truth to calibrate against. The human annotators are validating against the LLM output, not against an established VAD benchmark. This means the validation measures agreement between humans and the LLM, not accuracy.  
**Severity:** Medium — the paper may conflate agreement with accuracy. Reviewers will flag this.  
**Fix:** Add a calibration step. Before the main annotation task, have annotators score a small set (~50 posts) that have been independently scored using the NRC-VAD lexicon or the ANEW word list as a reference baseline. This establishes that the annotators' internal VAD scales are anchored to psychometric standards. Then the LLM-vs-human agreement becomes meaningful as a measure of the LLM's alignment with calibrated human judgment.

### FLAW-008: No Statistical Power Analysis (MEDIUM)

**Location:** Section 3.7  
**Description:** The validation sample is "approximately 5% of posts" per university. For 120,000 posts total, this is 6,000 posts reviewed by 8 annotators (750 per annotator). But there is no justification for why 5% is sufficient. A power analysis should determine the minimum sample size needed to detect a meaningful difference in Kappa or ICC at the target threshold (κ ≥ 0.70) with a specified confidence level.  
**Severity:** Medium — reviewers will question sample size adequacy.  
**Fix:** Conduct a power analysis for Cohen's Kappa. Using established formulas, determine the sample size needed to detect κ = 0.70 with 95% confidence and 80% power, given the expected number of categories and base rates. If the required sample is smaller than 5%, the current design is conservative and defensible. If larger, adjust the sample size.

### FLAW-009: No Handling of Post Length Distribution (LOW)

**Location:** Sections 3.3, 3.4  
**Description:** Freedom Wall posts vary dramatically in length — from one-word reactions to multi-paragraph confessions. The proposal does not address how extremely short posts (< 10 words) affect embedding quality or how extremely long posts (> 500 words) affect VAD scoring consistency. Short posts produce noisy embeddings; long posts may exceed the LLM's effective attention for scoring.  
**Severity:** Low — the embedding model handles variable lengths, and the 128K context window of the 70B model is not a constraint.  
**Fix:** Report the post length distribution in the results. Optionally, exclude posts below a minimum word count (e.g., < 5 words) as these are unlikely to contain meaningful sentiment. Document the exclusion criteria.

### FLAW-010: "Do No Harm" Protocol Operational Ambiguity (LOW)

**Location:** Section 3.9.4  
**Description:** The protocol flags posts with "high arousal and negative valence" containing self-harm keywords. But the system processes retrospective batch data with a 24-hour latency. A post flagged today may have been written months ago. The protocol implies urgency ("crisis heatmaps") but the data is not real-time. This creates a mismatch between the protocol's language and its actual capability.  
**Severity:** Low — the proposal does acknowledge retrospective data, but the language oscillates between "early warning" and "retrospective insight."  
**Fix:** Standardize the language. The system provides **retrospective risk pattern identification**, not real-time crisis detection. Rename "Crisis Heatmaps" to "Historical Distress Pattern Maps." Remove any language suggesting the system can intervene in ongoing situations.

### FLAW-011: JSON Flat-File Storage Not Scalable (LOW)

**Location:** Section 3.8  
**Description:** The dashboard uses JSON files read into Pandas DataFrames in memory. For 120,000 posts with embeddings (768-dimensional vectors), VAD scores, topic assignments, and engagement metrics, the in-memory footprint would be approximately 2-4GB. This is feasible on the development workstation but would cause issues on lower-spec machines or if the dataset grows.  
**Severity:** Low — acceptable for a prototype/research tool, but should be acknowledged as a scalability limitation.  
**Fix:** Acknowledge in the limitations section. For a production deployment, recommend migration to SQLite (single-file relational DB with no server requirements) or DuckDB (columnar analytics DB optimized for exactly this use case).

### FLAW-012: Missing Embedding Comparison with Pilot (LOW)

**Location:** Section 3.1  
**Description:** The pilot study used the same embedding model (paraphrase-multilingual-MiniLM-L12-v2) on SLU data and achieved coherence 0.58. The expanded study uses the same model on 12 universities. But the pilot's coherence score may not transfer — different institutions have different vocabularies, slang, and posting styles. The proposal does not plan to re-validate coherence on the expanded dataset.  
**Severity:** Low — coherence is computed per-university, so pilot results are not directly comparable anyway.  
**Fix:** Report per-university coherence scores in the results and compare against the pilot baseline. This is free information from the existing pipeline.

---

## 3. Action Log

### ACTION-001: LLM Migration Design

**Date:** 2026-05-01  
**Action:** Designed the migration path from local Llama-3-8B to NVIDIA NIM Llama 3.3 70B.  
**Verified:**
- Model `meta/llama-3.3-70b-instruct` is available on NVIDIA NIM
- API is OpenAI-compatible (chat completions endpoint)
- 128K context window confirmed
- 40 RPM free tier rate limit confirmed
- Python client: standard `openai` library with `base_url="https://integrate.api.nvidia.com/v1"`

**Decision:** Use the OpenAI Python SDK with base URL swap. This allows future migration to any OpenAI-compatible endpoint (OpenRouter, Together.ai, self-hosted) with zero code changes.

### ACTION-002: Batch Size Determination

**Date:** 2026-05-01  
**Action:** Evaluated batch sizes for VAD scoring (1, 5, 10, 20 posts per request).  
**Analysis:**
- Batch size 1: 120K requests at 40 RPM = 50 hours. Infeasible for iterative development.
- Batch size 5: 24K requests at 40 RPM = 10 hours. Feasible. JSON parsing complexity is manageable.
- Batch size 10: 12K requests at 40 RPM = 5 hours. Faster, but higher risk of cross-post confusion in model output and larger blast radius on parse failures.
- Batch size 20: 6K requests at 40 RPM = 2.5 hours. Prompt length approaches ~10K tokens. Model attention may degrade for posts later in the batch.

**Decision:** Batch size 5. Optimal balance between throughput and reliability. Each failed batch affects only 5 posts, and retrying 5 posts is cheap.

### ACTION-003: Sarcasm Detection Architecture

**Date:** 2026-05-01  
**Action:** Evaluated whether to keep sarcasm detection as a separate CoT step or integrate it into the VAD scoring prompt.

**Original Design:** Two-pass system. First pass: CoT prompt asks model to evaluate sarcasm markers. Second pass: VAD scoring prompt uses the sarcasm assessment to adjust scores. This doubles the API request count for affected posts.

**Revised Design:** Single-pass system. The VAD scoring prompt includes an instruction to internally assess sarcasm before scoring. The `sarcasm` boolean in the JSON output indicates whether the adjustment was made.

**Justification:** The 70B model's reasoning capability is sufficient for single-pass sarcasm-aware scoring. The 8B model needed the explicit CoT scaffolding because its reasoning was weaker — the 70B model can do this implicitly. A single-pass design halves the request count for posts that would have been flagged for sarcasm re-evaluation.

**Risk:** If sarcasm detection accuracy drops in single-pass mode, revert to two-pass for flagged posts only.

### ACTION-004: BERTopic Decoupling Design

**Date:** 2026-05-01  
**Action:** Designed the decoupled topic labeling pipeline.

**Implementation Plan:**
1. Run BERTopic with `representation_model=None` (or use the default c-TF-IDF representation)
2. After clustering, extract from each topic:
   - `topic.get_topic(topic_id)` → top-10 c-TF-IDF keywords
   - `topic.get_representative_docs(topic_id)` → top-5 representative documents
3. For each topic, construct the labeling prompt and call NIM API
4. Store labels in a separate mapping file: `{topic_id: label}`
5. Merge labels back into the BERTopic model using `topic_model.set_topic_labels(mapping)`

**Benefit:** This design means BERTopic's clustering output is immutable. Labels can be regenerated, refined, or manually overridden without re-running clustering. This is especially valuable for the HITL validation phase.

### ACTION-005: Anonymization Scheme Design

**Date:** 2026-05-01  
**Action:** Designed the institution anonymization codename scheme.

**Requirements:**
1. Preserve geographic clustering for cross-regional analysis
2. Preserve institutional type for public/private comparison
3. Prevent reverse-engineering through enrollment stats, department names, or geographic references

**Scheme:** `{CLUSTER}-{TYPE}-{INDEX}` (e.g., MM-PUB-1, CAR-PSEC-1)

**Cross-reference prevention layers:**
1. Department acronyms → generic codes (DEPT-ENG, DEPT-BUS, etc.)
2. Freedom Wall page names → redacted
3. Enrollment figures → reported as ranges
4. Campus landmarks → masked with `[CAMPUS_LOCATION]`
5. Post content referencing institution name → masked with `[UNIVERSITY]`

**Limitation:** Highly motivated readers familiar with Philippine HEIs could potentially narrow down institutions based on cluster + type + research context (e.g., there may be only one private sectarian university in the CAR cluster). This is acknowledged but considered acceptable for academic publication. Full anonymization would require removing the geographic clustering entirely, which would destroy a key analytical dimension.

### ACTION-006: Privacy Impact Assessment for Cloud API

**Date:** 2026-05-01  
**Action:** Assessed the privacy implications of sending anonymized post text to NVIDIA's servers.

**Findings:**
1. NVIDIA NIM free tier Terms of Use (Section 6) contain broad language about using "User Content" to "modify and improve NVIDIA products or services"
2. No explicit data retention period is specified for free-tier API calls
3. The Data Processing Addendum (DPA) provides stronger protections but applies primarily to enterprise customers
4. The API is stateless (no session, no stored context between calls) but server-side logging practices are opaque

**Decision:** Proceed with cloud API under the following conditions:
- ALL text sent to the API has already been anonymized (NER + regex + landmark masking)
- No post contains PII by the time it reaches the API
- The ethics section explicitly discloses cloud API usage
- If IRB objects, self-hosted NIM on a cloud GPU is the fallback (adds ~$33 cost for 11 hours on an A100)

### ACTION-007: Prompt Validation for 70B Model

**Date:** 2026-05-01  
**Action:** Analyzed prompt compatibility between 8B and 70B models.

**Identified Issues:**
1. The 70B model is more verbose — it tends to add explanations even when told not to. The "output ONLY the label" instruction must be reinforced with negative constraints.
2. The 70B model may produce Taglish labels (e.g., "Enrollment na Stress") if not explicitly told to output in English.
3. The 70B model's JSON compliance is higher than 8B's, but it occasionally wraps the JSON in markdown code blocks (```json ... ```). The response parser must strip these.
4. Temperature 0.1 on the 70B model produces near-deterministic output but not fully deterministic (unlike 0.0, which NIM may not support as exactly zero). Document this.

**Fixes Applied:**
- Added "In English" constraint to topic labeling prompt
- Added "No explanation, no punctuation, no quotes" to topic labeling prompt
- Added JSON code block stripping to response parser
- VAD scoring prompt uses structured JSON schema description

---

## 4. Edge Cases

### EDGE-001: Posts with Zero Content After Preprocessing

Some posts may be reduced to empty strings after regex cleaning, stopword removal, and NER masking. These "ghost posts" should be counted and reported but excluded from all analysis stages.

**Detection:** After preprocessing, check `len(cleaned_text.strip()) > 0`. Log the count per university.

### EDGE-002: Topics with Only 1-2 Representative Documents

HDBSCAN may create micro-clusters with very few documents, especially after the soft-clustering reassignment. These topics have too little evidence for reliable labeling.

**Handling:** Topics with fewer than 5 documents after reassignment are merged into a "Miscellaneous" meta-topic. Their documents are still included in VAD scoring but not in topic-level aggregation.

### EDGE-003: VAD Scores at Scale Boundaries

The SAM scale is 1-9. The LLM may occasionally output 0 or 10, or non-integer values (e.g., 7.5). 

**Handling:** Clamp all values to [1, 9]. Round non-integers to nearest integer. Log the frequency of out-of-range values as a quality indicator.

### EDGE-004: Bilingual Posts Where Taglish Ratio is Ambiguous

The inclusion criterion requires "at least 50% Taglish content." But measuring Taglish percentage is non-trivial — is it by word count, character count, or sentence count? A post with 10 English words and 5 Tagalog words is 33% Tagalog by word count but may be "100% Taglish" by register.

**Handling:** Use a practical heuristic: if the post contains at least one Tagalog word or phrase (detected by a Tagalog word list), it is included. Pure English posts with no code-switching are still included (many Freedom Wall posts are in English). The 50% threshold from the proposal is relaxed to a binary "contains Tagalog or is English" criterion. This is more defensible and easier to implement.

**Justification:** The embedding model (paraphrase-multilingual-MiniLM-L12-v2) handles both English and Tagalog. Excluding purely English posts would lose valid student discourse. The 50% Taglish requirement in the original proposal is unnecessarily restrictive and difficult to operationalize.

### EDGE-005: API Timeout During Long Batch

If the NIM API times out mid-batch (e.g., during a 5-post VAD scoring request), the entire batch must be retried.

**Handling:** Set a 30-second timeout per request. On timeout, retry with exponential backoff. If the batch fails 5 times, split it into individual requests (batch size 1) and retry each post separately. Log the split.

### EDGE-006: Duplicate Posts Across Universities

Some Freedom Wall pages reshare posts from other universities, or students cross-post. The same text may appear in multiple university datasets.

**Handling:** After preprocessing, compute text hashes (SHA-256 of cleaned text) across all universities. If duplicates are found, keep only the earliest instance (by timestamp). Log the deduplication count.

### EDGE-007: Seasonal Data Gaps

Some university Freedom Walls may have posting gaps (e.g., during summer break, or if the page admin goes inactive). These gaps affect the temporal analysis module.

**Handling:** The temporal analysis module should interpolate or mark data gaps explicitly rather than showing them as "zero sentiment." A post-count timeline alongside the sentiment timeline makes gaps visible to the dashboard user.

### EDGE-008: Freedom Wall Page Takedown Mid-Research

A Freedom Wall page may be deleted, privatized, or renamed during the data collection period. Historical data already collected is still valid, but new scraping runs will fail.

**Handling:** Complete all scraping for all universities in a single batch window (1-2 days). Do not rely on incremental scraping over weeks. If a page disappears after scraping, the data is still usable.

---

## 5. Rejected Ideas

### REJECTED-001: Fine-Tuning Llama 3.3 70B on Taglish Data

**Idea:** Fine-tune the 70B model on a Taglish sentiment dataset to improve VAD scoring accuracy.  
**Rejection Reason:** Fine-tuning a 70B model requires significant compute (8× A100 GPUs for several hours), is expensive, and introduces model versioning complexity. The few-shot prompting approach with the base model is sufficient for the research scope. Fine-tuning is a valid future work direction but is out of scope for this study.

### REJECTED-002: Real-Time Streaming Pipeline

**Idea:** Replace batch processing with a real-time streaming pipeline (e.g., Kafka + Spark Streaming) that processes posts as they are published.  
**Rejection Reason:** This would require persistent authenticated access to Facebook's API or a webhooks integration that does not exist for third-party pages. The 24-hour batch cycle is the correct architectural choice for the ethical and technical constraints of this study.

### REJECTED-003: Using NVIDIA NIM Embedding API Instead of Local Model

**Idea:** Use NIM's embedding endpoints instead of the local paraphrase-multilingual-MiniLM-L12-v2 model.  
**Rejection Reason:** The local embedding model is lightweight (~420MB), runs on CPU in seconds for the full dataset, and produces deterministic results. Adding an API dependency for embeddings would increase latency, cost, and complexity with no quality benefit. The NIM embedding models are English-centric and less tested on Tagalog than the multilingual SentenceTransformers model.

### REJECTED-004: Closed-source frontier LLM API for VAD Scoring

**Idea:** Use a larger closed-source proprietary frontier-tier LLM (via a third-party API) for higher-quality VAD scoring.  
**Rejection Reason:** (1) The methodology specification mandates NVIDIA NIM + Llama 3.3 70B. (2) Closed-source API providers introduce per-token cost at scale (typically several dollars per million tokens). (3) Closed-source weights are not inspectable, reducing reproducibility. (4) The 70B Llama model's reasoning capability is sufficient for VAD scoring based on benchmark performance.

### REJECTED-005: Using Facebook Graph API Instead of Scraping

**Idea:** Use Facebook's official Graph API to collect Freedom Wall posts.  
**Rejection Reason:** The Graph API requires the page administrator to grant API access. Freedom Walls are run by anonymous student admins who are unlikely to cooperate with a research team. Additionally, the Graph API provides structured data but requires an active Facebook App with approved permissions — a process that can take weeks and may not be approved for research on anonymous posts.

### REJECTED-006: Translating All Posts to English Before Analysis

**Idea:** Use a machine translation model to convert all posts to English, then use English-only NLP tools.  
**Rejection Reason:** The proposal correctly identifies this as destructive. Taglish code-switching carries semantic and emotional information (e.g., switching to Tagalog for emotional emphasis). Translation strips this signal. The entire methodology is designed around preserving the original language, and the embedding model is multilingual. Translation would undermine the study's core contribution.

### REJECTED-007: Reducing Scope to Fewer Universities

**Idea:** Cut the 12-university scope to 4-6 to reduce processing time and complexity.  
**Rejection Reason:** The 12-university scope is one of the paper's primary contributions over the pilot (which used only 1 university). Reducing scope would weaken the claim of generalizability and make the paper less competitive for publication. The API-based inference approach makes 12 universities feasible within the time budget.

### REJECTED-008: Using BERTopic's Built-in OpenAI Representation

**Idea:** BERTopic has an `OpenAI` representation model class. Since NIM is OpenAI-compatible, use it directly.  
**Rejection Reason:** Evaluated and found viable but rejected for control reasons. The built-in `OpenAI` class handles the API call internally, which means error handling, retry logic, and response caching must be monkey-patched or overridden. Decoupling labeling from BERTopic gives full control over the API interaction layer, which is critical for a pipeline making 1,000+ API calls with a 40 RPM rate limit.

---

## 6. Optimization Decisions

### OPT-001: Per-University vs. Global Topic Modeling — Preserved

The original proposal runs BERTopic separately per university. This was re-evaluated.

**Global model advantages:** Cross-university topic comparison at the vector level, not just the label level. Larger corpus may produce more stable topics.

**Global model disadvantages:** Campus-specific vocabulary (e.g., local landmarks, department acronyms) gets diluted. A topic about "enrollment" at one university may cluster with "enrollment" at another despite referring to completely different systems. The anonymization requirement makes cross-university vector-level comparison less meaningful.

**Decision:** Preserve per-university modeling. Cross-university comparison happens at the label level (comparing topic labels across institutions) rather than the vector level. This is consistent with the anonymization strategy.

### OPT-002: Checkpoint Granularity

**Options:**
- Per-request checkpointing (write after every API call)
- Per-batch checkpointing (write after every N requests)
- Per-university checkpointing (write after completing each university)

**Decision:** Write checkpoint after every 100 successful requests. This balances disk I/O overhead against data loss risk. At 40 RPM, 100 requests = 2.5 minutes of work. Maximum data loss on crash: 2.5 minutes of inference.

### OPT-003: Response Caching Strategy

All API responses are cached locally in a structured directory:

```
cache/
  topic_labels/
    {university_code}/
      topic_{id}.json        # prompt + response + metadata
  vad_scores/
    {university_code}/
      batch_{number}.json    # prompt + response + metadata
```

This cache serves three purposes:
1. Avoid re-processing on restart (complement to checkpoint)
2. Enable post-hoc audit of every LLM decision
3. Provide reproducibility evidence for reviewers

### OPT-004: Few-Shot Example Selection for VAD

**Original:** "Linguistically verified examples of rare Taglish sentiment expressions" — not specified.

**Revised:** Three hardcoded few-shot examples in the VAD prompt, covering:
1. Low-Valence, Low-Arousal, Low-Dominance (burnout/depression): A Taglish post expressing academic exhaustion with passive language
2. Low-Valence, High-Arousal, Low-Dominance (rage/frustration): A Taglish post expressing anger at institutional failure
3. High surface-Valence with sarcasm (false positive trap): A Taglish post using ironic praise

These three examples anchor the model's understanding of the VAD space extremes and the sarcasm trap. They are drawn from the pilot study dataset and verified by the research team.

### OPT-005: Lazy-Label Detection Thresholds

The original proposal mentions detecting "lazy labels" like "Student Life" or "General Concerns." The 70B model is less likely to produce these, but the detection script is preserved with an expanded blocklist:

```python
LAZY_LABELS = [
    "Student Life", "General Concerns", "University Issues",
    "Campus Life", "Student Experiences", "Various Concerns",
    "Mixed Topics", "General Discussion", "Student Posts",
    "Miscellaneous", "Other Topics", "Random Posts"
]
```

Any generated label matching this list (case-insensitive, partial match) is flagged for regeneration with a more specific prompt that emphasizes the representative documents over the keywords.

---

## 7. Ethical Review

### ETH-001: Cloud API Data Transmission Disclosure

**Original assumption:** All data stays on local, encrypted, air-gapped workstation.  
**New reality:** Anonymized text is transmitted to NVIDIA servers via HTTPS.

**Required disclosure in ethics section:**
- Anonymized post text is processed by NVIDIA's cloud infrastructure
- No PII reaches the API (verified by pre-API anonymization pipeline)
- NVIDIA's Terms of Use permit use of submitted content for service improvement
- The research team cannot verify NVIDIA's internal data handling practices for free-tier users
- Self-hosted NIM is available as a fallback if institutional ethics review requires it

### ETH-002: Informed Consent Gap

Freedom Wall posts are publicly accessible but written with no expectation of being analyzed by AI systems. The proposal addresses this under "legitimate institutional interest" but does not consider:
- Whether students would object to their anonymous posts being sentiment-scored by a 70B language model
- Whether the transformation from "anonymous social media post" to "data point with VAD scores" crosses an ethical line that public accessibility alone does not justify

**Assessment:** This is an inherent tension in computational social science research on public social media data. The proposal's position (publicly accessible = analyzable) is consistent with standard practice in the field. The anonymization, data minimization, and aggregate-only reporting provide adequate safeguards. The ethics section should acknowledge the tension explicitly rather than dismissing it.

### ETH-003: Potential for Institutional Misuse

The dashboard is designed for "administrative decision-making." But the proposal does not address how the tool could be misused:
- An administration could use sentiment data to identify and suppress dissent
- Department-level sentiment could be used to punish low-scoring departments
- Temporal spikes in negative sentiment could be used to time PR campaigns rather than address root causes

**Recommendation:** Add a "Responsible Use" section to the dashboard documentation. Include explicit statements that the tool is for aggregate pattern identification, not individual tracking, and that sentiment data should inform support services, not punitive measures.

### ETH-004: Annotator Welfare

The 8 human annotators will read Freedom Wall posts that may contain distressing content (self-harm ideation, sexual harassment reports, bullying). The proposal's training protocol mentions "processed ambiguous or potentially unhealthy content" but does not describe support measures for annotators.

**Recommendation:** Add to the HITL protocol:
1. Annotators may skip any post they find personally distressing without penalty
2. Annotator sessions are limited to 2 hours maximum with mandatory breaks
3. Contact information for university counseling services is provided to all annotators
4. Any post containing graphic descriptions of self-harm is pre-screened and optionally excluded from annotation tasks

---

## 8. Open Questions for the Research Team

### Q1: Apify Actor Authentication Verification

Has the specific Apify Facebook Page Scraper actor been tested in unauthenticated mode? Does it produce results for all 12 target Freedom Wall pages without a Facebook session cookie? This must be verified before data collection begins.

### Q2: IRB / Ethics Board Status

Has the research been submitted to Saint Louis University's ethics review board? The proposal mentions compliance with the National Privacy Commission and UP Data Privacy Notice but does not reference SLU's own ethics review process. Cloud API usage must be disclosed in the ethics application.

### Q3: Few-Shot Example Availability

Are the three few-shot examples for VAD scoring available from the pilot study? They need to be finalized before the VAD inference pipeline is built. The examples must cover the three anchor points (burnout, rage, sarcasm) and be verified by the team as correctly scored.

### Q4: Annotator Recruitment Status

Are the 8 annotators already recruited? The calibration workshop and pilot annotation rounds (100-200 posts) need to happen before the main validation task. If annotators are not yet recruited, this is on the critical path.

### Q5: NVIDIA NIM API Key

Has an NVIDIA Developer account been created and an API key generated? The free tier provides 40 RPM immediately, but account creation requires verification.

### Q6: Engagement Metrics Decision

Does the team want to use engagement metrics (likes, shares, comments) in the analysis, or should they be dropped? The current methodology collects them but does not analyze them. A decision is needed before preprocessing begins.

### Q7: RoBERTa-Tagalog Ablation Decision

Does the team want to run the ablation study (Path A in FLAW-006), comparing paraphrase-multilingual-MiniLM-L12-v2 against RoBERTa-Tagalog? This doubles the embedding + clustering compute time but adds a genuine methodological contribution.

### Q8: Post Length Minimum

Should posts below a minimum word count be excluded? If so, what threshold? The proposal does not specify. A reasonable minimum is 5 words — posts shorter than this (e.g., "lol", "same", "totoo") cannot carry meaningful topic or sentiment signal.

---

## 9. Implementation Priority Order

Based on the analysis above, the recommended execution sequence is:

| Priority | Task | Dependency | Estimated Duration |
|---|---|---|---|
| 1 | Verify Apify scraper works unauthenticated for all 12 pages | None | 1-2 days |
| 2 | Set up NVIDIA NIM API key and test basic inference | None | 1 day |
| 3 | Run scraping for all 12 universities in a single batch | P1 | 2-3 days |
| 4 | Build and test preprocessing pipeline | P3 | 3-5 days |
| 5 | Build and test anonymization pipeline (NER + landmarks + institution codes) | P4 | 2-3 days |
| 6 | Run BERTopic per university (primary embedding model) | P5 | 2-3 days |
| 7 | (Optional) Run BERTopic per university (RoBERTa-Tagalog ablation) | P5 | 2-3 days |
| 8 | Build API client with rate limiter, retry, checkpoint | P2 | 2-3 days |
| 9 | Run topic labeling via NIM API | P6, P8 | 1 day |
| 10 | Run VAD scoring via NIM API | P6, P8, P9 | 1-2 days |
| 11 | Build post-processing + validation (lazy-label detection, schema validation) | P9, P10 | 2 days |
| 12 | Recruit and train annotators | None (start early) | 1-2 weeks |
| 13 | Run HITL validation in Label Studio | P11, P12 | 2-3 weeks |
| 14 | Compute IRR metrics (Kappa, ICC) | P13 | 2-3 days |
| 15 | Build dashboard | P11 | 1-2 weeks |
| 16 | Write results + analysis | P14, P15 | 2-3 weeks |

**Critical Path:** P1 → P3 → P4 → P5 → P6 → P8 → P9 → P10 → P11 → P13 → P14 → P16

**Estimated Total Duration:** 10-14 weeks (assuming 8 annotators are available within 2 weeks of recruitment start)

---

*End of Execution Log*
