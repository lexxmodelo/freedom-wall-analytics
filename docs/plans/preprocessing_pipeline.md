# Freedom Wall Data Cleaning & Preprocessing Pipeline

## Context

Thesis: *"AI-Driven Topic Modeling and Multidimensional Sentiment Analysis of Student Discourse on Philippine University Freedom Walls."*

Raw data has been scraped into JSONL files at [scraper_project/data/](scraper_project/data/). Three of twelve target universities are scraped today (`SLU.jsonl`, `FW-01.jsonl` = ADMU, `FW-02.jsonl` = UPLB), totalling ~12,016 posts. Each line contains `text`, `timestamp_iso` (mostly `null`), `timestamp_raw` (e.g. `"May 2, 2026 8:46:27 AM HKT"`), `engagement`, `post_url`, `post_id`, `source`.

**Why this work is needed.** Before topic modeling (BERTopic) and VAD sentiment analysis can run, raw posts must be (1) anonymized to remove **all** school-identifying signal — keeping only one of three regional tags `[Metro Manila]` / `[Luzon/Provincial]` / `[Baguio/Benguet]` — (2) cleaned of scraping artifacts, URLs, PII, and student IDs, (3) NER-redacted for personal/professor/department names, (4) language-classified (English / Filipino / Taglish), and (5) deduplicated. This pipeline implements Section 3.3 of the thesis methodology, adapted per Section 3.9.1 (data minimization) so that **no school name remains** in the output dataset.

**Adaptation from the proposal.** Section 3.3.6 originally called for "Academic Unit Categorization" with explicit university tagging. We are deliberately replacing this with regional generalization to honor the data-minimization commitment. Researchers can still analyze geographic patterns (urban vs. provincial vs. highland) without exposing institutional identity.

**Decisions confirmed with user.** Pipeline targets all 12 universities (auto-handles the 9 unscraped once their JSONL arrives); NER uses local spaCy `en_core_web_lg` + curated Tagalog name list; cross-university posts are kept (anonymized to overlapping region tags); project lives at [preprocessing/](preprocessing/) sibling to `scraper_project/`.

---

## Output contract

Three UTF-8 JSON files in [preprocessing/output/](preprocessing/output/):

- `metro_manila_posts.json` (UPD, DLSU, ADMU, FEU, PUP)
- `luzon_provincial_posts.json` (UPLB, LPU-B, CSU)
- `baguio_benguet_posts.json` (UPB, BSU, UB, SLU)

Each post object — **only these fields, nothing else**:

```json
{
  "post_id": "84bc05d5a17747f2",
  "text": "...cleaned and anonymized...",
  "engagement": {"reactions": 0, "comments": 1, "shares": 0},
  "timestamp_unix": 1746140787,
  "region": "Baguio/Benguet",
  "language_detected": "Taglish"
}
```

Plus support files: `_rejected.jsonl` (dropped posts + reason + phase), `_qc_report.json` (counts, language histogram, leak audit, dedup stats).

---

## Folder layout

```
C:\Users\Alex Evan\Documents\Research\preprocessing\
├── README.md
├── requirements.txt
├── pyproject.toml
├── preprocessing\
│   ├── __init__.py
│   ├── run.py                       # CLI entry-point
│   ├── pipeline.py                  # phase orchestrator + I/O
│   ├── io_utils.py
│   ├── phase01_select.py
│   ├── phase02_anonymize_school.py
│   ├── phase03_noise_regex.py
│   ├── phase04_ner.py
│   ├── phase05_linguistic.py
│   ├── phase06_stopwords.py         # flag only, do not strip
│   ├── phase07_engagement.py
│   ├── phase08_timestamps.py
│   ├── phase09_language.py
│   ├── phase10_dedupe_qc.py
│   ├── regex_lib.py
│   ├── schools.py                   # YAML loader + dataclass
│   ├── name_lists.py
│   └── logging_setup.py
├── configs\
│   ├── schools.yaml                 # 12-school dictionary (editable)
│   ├── stopwords_tagalog.txt
│   ├── stopwords_english.txt
│   └── tagalog_given_names.txt      # ~2k common PH given names from PSA data
├── fixtures\
│   ├── golden_input.jsonl           # 20 hand-crafted posts
│   └── golden_expected.json
├── tests\
│   ├── test_phase02_anonymize.py
│   ├── test_phase03_regex.py
│   ├── test_phase04_ner.py
│   ├── test_phase08_timestamps.py
│   ├── test_phase09_language.py
│   ├── test_pipeline_e2e.py
│   └── test_no_school_leaks.py      # hard assertion: no school name remains
└── output\
    ├── metro_manila_posts.json
    ├── luzon_provincial_posts.json
    ├── baguio_benguet_posts.json
    ├── _rejected.jsonl
    └── _qc_report.json
```

---

## Phase-by-phase responsibilities

The orchestrator in [preprocessing/pipeline.py](preprocessing/pipeline.py) reads each JSONL line and routes it through phases 1→10 in order. Intermediate JSONL is written to `output/_intermediate/phaseNN.jsonl` so any single phase can be rerun without redoing earlier work.

| # | Module | Responsibility |
|---|---|---|
| 01 | `phase01_select.py` | Drop everything except `text, timestamp_iso, timestamp_raw, engagement, post_url, post_id, source`. Drop posts with empty/null `text`. NFKC-normalize unicode immediately. |
| 02 | `phase02_anonymize_school.py` | Replace every school identifier with its region tag. See **§Anonymization order** and **§Linguistic-preserve rule** below. |
| 03 | `phase03_noise_regex.py` | Strip `Submitted:`, `See more`, ellipsis trails, URLs, emails, PH phone numbers, stray digit runs ≥4 (student IDs), normalize 4+ char repeats → 3, collapse whitespace. |
| 04 | `phase04_ner.py` | spaCy `en_core_web_lg` PERSON spans → `[REDACTED_NAME]`; Tagalog name-list pass; `Sir/Maam/Prof/Dr/Engr` + capitalized name → `[PROFESSOR_NAME]`; department keyword pass → `[DEPARTMENT]`. **Runs BEFORE Phase 03 punctuation/case normalization** to preserve spaCy recall — see §Risks. |
| 05 | `phase05_linguistic.py` | Sanity passthrough: assert no machine translation occurred; verify NFKC; preserve Taglish exactly. Carries `text` through with optional `tokens` field for downstream RoBERTa-Tagalog tokenizer. |
| 06 | `phase06_stopwords.py` | Add `stopword_flags` field listing pragmatic-particle counts (`po, naman, lang, pala, kase, ba, eh, kaso`) for downstream c-TF-IDF. **Do not remove yet.** Final output drops this field — it's used by the next research stage, not by the cleaned corpus consumer. |
| 07 | `phase07_engagement.py` | Coerce `reactions, comments, shares` to int; null → 0. |
| 08 | `phase08_timestamps.py` | Parse `timestamp_raw` (strip trailing `HKT/PHT/GMT+8/UTC+8/PST` token first, then delegate to `scraper_project.utils.parse_absolute_timestamp`); fallback to `timestamp_iso`; coerce to Asia/Manila (PHT, UTC+8); emit `timestamp_unix` as int epoch. Posts with unparseable timestamps → `_rejected.jsonl` reason `"unparseable_timestamp"`. |
| 09 | `phase09_language.py` | Classify English / Filipino / Taglish via `py3langid` + token-ratio heuristic (see §Language detection). Posts classified as Ilokano/Kapampangan/Cebuano → `_rejected.jsonl` reason `"regional_dialect"`. |
| 10 | `phase10_dedupe_qc.py` | Exact dedupe via `scraper_project.utils.post_hash` on cleaned text; near-dup via MinHash/LSH at Jaccard 0.9; quality gate (drop posts <10 chars, pure-media, spam patterns); bucket by region; write three output files + `_qc_report.json`. |

---

## Critical files to create / modify

- [preprocessing/preprocessing/phase02_anonymize_school.py](preprocessing/preprocessing/phase02_anonymize_school.py) — anonymization core
- [preprocessing/preprocessing/regex_lib.py](preprocessing/preprocessing/regex_lib.py) — all compiled patterns
- [preprocessing/configs/schools.yaml](preprocessing/configs/schools.yaml) — 12-school master dictionary
- [preprocessing/preprocessing/pipeline.py](preprocessing/preprocessing/pipeline.py) — orchestrator
- [preprocessing/preprocessing/phase08_timestamps.py](preprocessing/preprocessing/phase08_timestamps.py) — TZ-suffix wrapper around the existing parser

## Reused (read-only) from `scraper_project/`

- [scraper_project/utils.py:post_hash](scraper_project/utils.py) — exact-dedup hashing
- [scraper_project/utils.py:parse_absolute_timestamp](scraper_project/utils.py) — date parser (wrap to strip `HKT` first)
- [scraper_project/utils.py:PHT](scraper_project/utils.py) — Asia/Manila tzinfo constant
- [scraper_project/utils.py:setup_logger](scraper_project/utils.py) — logging style
- [scraper_project/config.py:TARGETS](scraper_project/config.py) — scraper-code → URL mapping (cross-reference for `scraper_code` field in `schools.yaml`)

---

## Master school dictionary (`configs/schools.yaml`)

12 entries. Each carries a `data_confidence` flag (`high|medium|low|guess`) so the researcher knows which entries to verify against the actual Facebook page before relying on production output. **Verify low/guess entries with the thesis advisor before final run.**

```yaml
- canonical_acronym: ADMU
  full_name_variations: [Ateneo de Manila University, Ateneo de Manila, Ateneo]
  freedom_wall_hashtag_pattern: '(?i)#ADMU(?:FW|FreedomWall)\d*'
  scraper_code: FW-01
  location_markers:
    - {phrase: Katipunan,        semantic_replace: true}
    - {phrase: Loyola Heights,   semantic_replace: true}
  mascot_cheer_terms: [Blue Eagles, Blue Eagle, One Big Fight, Halikinu]
  region: Metro Manila
  data_confidence: high

- canonical_acronym: UPD
  full_name_variations: [University of the Philippines Diliman, UP Diliman]
  freedom_wall_hashtag_pattern: '(?i)#UPD(?:FW|FreedomWall)\d*'
  scraper_code: FW-02
  location_markers:
    - {phrase: Diliman,          semantic_replace: true}
    - {phrase: AS Walk,          semantic_replace: true}
    - {phrase: Sunken Garden,    semantic_replace: true}
  mascot_cheer_terms: [Fighting Maroons, UP Fight]   # "Maroons" alone -> ambiguous, see §Edge cases
  region: Metro Manila
  data_confidence: high

- canonical_acronym: DLSU
  full_name_variations: [De La Salle University, La Salle]
  freedom_wall_hashtag_pattern: '(?i)#DLSU(?:FW|FreedomWall)\d*'
  scraper_code: null            # not yet scraped
  location_markers:
    - {phrase: Taft Avenue,      semantic_replace: true}
  mascot_cheer_terms: [Green Archers, Animo La Salle]
  region: Metro Manila
  data_confidence: high

- canonical_acronym: FEU
  full_name_variations: [Far Eastern University]
  freedom_wall_hashtag_pattern: '(?i)#FEU(?:FW|FreedomWall)\d*'
  scraper_code: FW-03
  location_markers:
    - {phrase: Morayta,          semantic_replace: true}
    - {phrase: Nicanor Reyes,    semantic_replace: true}
  mascot_cheer_terms: [Tamaraws, Tamaraw, Go Tams]
  region: Metro Manila
  data_confidence: high

- canonical_acronym: PUP
  full_name_variations: [Polytechnic University of the Philippines, PUP Sta. Mesa]
  freedom_wall_hashtag_pattern: '(?i)#PUP(?:FW|FreedomWall)\d*'
  scraper_code: null
  location_markers:
    - {phrase: Sta. Mesa,        semantic_replace: true}
    - {phrase: Mabini Campus,    semantic_replace: true}
  mascot_cheer_terms: [Mighty Maroons]   # ambiguous with UPD/UPB Maroons
  region: Metro Manila
  data_confidence: high

- canonical_acronym: UPLB
  full_name_variations: [University of the Philippines Los Baños, UP Los Banos, UP Los Baños]
  freedom_wall_hashtag_pattern: '(?i)#UPLB(?:FW|FreedomWall)\d*'
  scraper_code: FW-04            # also FW-02 in current data — see §Discrepancies
  location_markers:
    - {phrase: Los Baños,        semantic_replace: true}
    - {phrase: Los Banos,        semantic_replace: true}
    - {phrase: Mt Makiling,      semantic_replace: true}
  mascot_cheer_terms: [Aggies]
  region: Luzon/Provincial
  data_confidence: medium

- canonical_acronym: LPU-B
  full_name_variations: [Lyceum of the Philippines University Batangas, Lyceum Batangas, LPU Batangas]
  freedom_wall_hashtag_pattern: '(?i)#LPUB(?:FW|FreedomWall)\d*'
  scraper_code: FW-05
  location_markers:
    - {phrase: Capitol Site,     semantic_replace: true}
  mascot_cheer_terms: [Pirates]   # verify on Facebook page
  region: Luzon/Provincial
  data_confidence: low

- canonical_acronym: CSU
  full_name_variations: [Cagayan State University, Caraga State University]   # disambiguate which one — verify
  freedom_wall_hashtag_pattern: '(?i)#CSU(?:FW|FreedomWall)\d*'
  scraper_code: FW-06
  location_markers: []
  mascot_cheer_terms: []
  region: Luzon/Provincial
  data_confidence: guess

- canonical_acronym: UPB
  full_name_variations: [University of the Philippines Baguio, UP Baguio]
  freedom_wall_hashtag_pattern: '(?i)#UPB(?:FW|FreedomWall)\d*'
  scraper_code: FW-07
  location_markers:
    - {phrase: Governor Pack,    semantic_replace: true}
  mascot_cheer_terms: []         # "Maroons" collides with UPD; do not list
  region: Baguio/Benguet
  data_confidence: medium

- canonical_acronym: BSU
  full_name_variations: [Benguet State University]
  freedom_wall_hashtag_pattern: '(?i)#BSU(?:FW|FreedomWall)\d*'
  scraper_code: FW-08
  location_markers:
    - {phrase: La Trinidad,      semantic_replace: true}
  mascot_cheer_terms: [Mountaineers]   # verify
  region: Baguio/Benguet
  data_confidence: low

- canonical_acronym: UB
  full_name_variations: [University of Baguio]
  freedom_wall_hashtag_pattern: '(?i)#UB(?:FW|FreedomWall|Files)\d*'
  scraper_code: FW-09
  location_markers: []
  mascot_cheer_terms: [Cardinals]      # verify
  region: Baguio/Benguet
  data_confidence: low

- canonical_acronym: SLU
  full_name_variations: [Saint Louis University, St. Louis University]
  freedom_wall_hashtag_pattern: '(?i)#SLU(?:FW|FreedomWall)\d*'
  scraper_code: SLU
  location_markers:
    - {phrase: Maryheights,      semantic_replace: true}
    - {phrase: Bonifacio St,     semantic_replace: true}
    - {phrase: Navy Base,        semantic_replace: true}
  mascot_cheer_terms: [Navigators, Go Navs]
  region: Baguio/Benguet
  data_confidence: high
```

---

## Regex library (`regex_lib.py`)

```python
PATTERNS = {
    "indexing_hashtag":  re.compile(r'(?i)#[A-Z]{2,6}(?:FW|FreedomWall|Files)\d+'),
    "submitted_prefix":  re.compile(r'^\s*Submitted\s*:\s*', re.IGNORECASE | re.MULTILINE),
    "see_more":          re.compile(r'\.{3,}\s*See\s*more\b', re.IGNORECASE),
    "ellipsis_trail":    re.compile(r'\s*\.{3,}\s*$'),
    "url":               re.compile(r'https?://\S+|www\.\S+|\b\S+\.(?:com|net|org|ph|edu)(?:/\S*)?'),
    "email":             re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b'),
    "phone_ph":          re.compile(r'(?:\+?63|0)9\d{2}[-\s]?\d{3}[-\s]?\d{4}|\(0?2\)\s*\d{3,4}[-\s]?\d{4}'),
    "student_id":        re.compile(r'(?<!\w)\d{4,}(?!\w)'),
    "char_repeat":       re.compile(r'(.)\1{3,}'),                  # replace with r'\1\1\1'
    "whitespace":        re.compile(r'\s+'),
    "professor_title":   re.compile(
        r'\b(?:Sir|Ma\'?am|Prof(?:essor)?|Dr|Engr|Atty)\.?\s+'
        r'([A-Z][a-zàáéíóúñ]+(?:\s+[A-Z][a-zàáéíóúñ]+){0,2})'
    ),
    "tz_suffix":         re.compile(r'\s+(?:HKT|PHT|GMT[+-]\d+|UTC[+-]\d+|PST)\s*$', re.IGNORECASE),
    "pure_media":        re.compile(r'^\s*(?:\[photo\]|\[video\]|\[image\])?\s*$', re.IGNORECASE),
}
```

School-replacement patterns are **built at runtime** from `schools.yaml`, not hard-coded here.

---

## Anonymization order (Phase 02)

Apply replacements in this strict order. Reason: longer/more-specific tokens shadow shorter ones, so e.g. `UP` won't accidentally match inside `UPLB`.

1. **Indexing hashtags** (`#ADMUFW123`, `#SLUFreedomWall25117`) — most unambiguous; gives an early definitive region tag.
2. **Multi-word full names** (`Ateneo de Manila University`, `University of the Philippines Los Baños`) — descending length.
3. **Two-word names** (`UP Diliman`, `UP Baguio`) — must come before bare `UP`.
4. **Location markers** with `semantic_replace: true` — see linguistic-preserve rule below.
5. **Mascot/cheer phrases** (`Blue Eagles`, `One Big Fight`).
6. **Single-word school names** (`Ateneo`, `Lyceum`).
7. **Acronyms, longest first**: `UPLB → LPU-B → DLSU → ADMU → UPD → UPB → FEU → PUP → BSU → CSU → SLU → UB → UP`. Always wrap in `\b...\b`; for ambiguous short ones (`UP`, `UB`) use `(?<![#A-Za-z])UP\b(?![A-Za-z])`.

After all substitutions, collapse runs like `[Metro Manila] [Metro Manila]` to a single tag.

---

## Linguistic-preserve vs. strip rule

For each location marker `M` with `semantic_replace: true`:

```
if M appears as standalone token AND (
     preceded by a Filipino preposition {sa, ng, mula, papuntang, galing}
     OR preceded by an English preposition {in, at, near, around, from, to}
     OR followed by a discourse-relevant noun {traffic, jeep, jam, area, vibe, weather}
   ):
     INLINE replace with " [REGION_TAG] "    # preserves grammar
else if M appears at start of post immediately followed by ":" or "—":
     DROP entirely                          # it's a location stamp, not discourse
else:
     INLINE replace                         # default = preserve linguistic context
```

Concretely:
- `"wala nang jeep sa Katipunan grabe"` → `"wala nang jeep sa [Metro Manila] grabe"` (preserve)
- `"Katipunan: parang naloko ako"` → `"parang naloko ako"` (drop the stamp)

**`Manila` and `Baguio` alone are never replaced** — too generic. Only their school-pairing variants (`UP Baguio`, `Manila campus`, etc.) trigger anonymization.

---

## NER strategy (Phase 04)

Local-only, three layers:

1. **spaCy `en_core_web_lg`** for `PERSON` spans → `[REDACTED_NAME]`. Strong on English-orthographic Filipino names (`Maria Cruz`, `Juan dela Cruz`).
2. **Curated Tagalog given-name list** at `configs/tagalog_given_names.txt` (~2k entries from PSA name-frequency data). Word-boundary case-sensitive match → `[REDACTED_NAME]`. Catches purely Filipino names spaCy misses.
3. **`professor_title` regex** → `[PROFESSOR_NAME]` — captures `Sir/Ma'am/Prof/Dr/Engr/Atty` + 1–3 capitalized tokens.
4. **Department keyword list** → `[DEPARTMENT]` — common acronyms (CSSP, GCOE, SAMCIS, COE, CBA, etc.) plus phrases like `Department of <X>`, `College of <Y>`.

**Phase 04 runs before Phase 03 punctuation/case normalization** so spaCy keeps the casing/punctuation it depends on for entity recall.

---

## Language detection (Phase 09)

**Library:** `py3langid` (deterministic, lightweight, supports Tagalog `tl`).

**Heuristic for Taglish** (token-ratio over function words):

```python
TAGALOG_FUNC = {"ang","ng","mga","sa","ay","na","at","kasi","talaga","naman",
                "lang","din","rin","yung","ito","ako","ikaw","siya","kami",
                "tayo","kayo","sila","po","opo","hindi","oo","wala","may"}
ENGLISH_FUNC = {"the","a","an","of","to","in","is","that","this","you","i",
                "my","with","for","on","but","not","be","have","do"}

toks = re.findall(r"[A-Za-z']+", text.lower())
tl_ratio = sum(1 for t in toks if t in TAGALOG_FUNC) / max(len(toks), 1)
en_ratio = sum(1 for t in toks if t in ENGLISH_FUNC) / max(len(toks), 1)
primary  = py3langid.classify(text)[0]

if tl_ratio >= 0.05 and en_ratio >= 0.05:    return "Taglish"
if primary == "tl" or tl_ratio > en_ratio:   return "Filipino"
if primary == "en":                          return "English"
if primary in {"ilo","pam","ceb","war","hil"}: return "Other"  # → reject
```

Threshold 0.05 ≈ 1 function word per 20 tokens; tune on golden fixture.

---

## Near-duplicate detection (Phase 10)

`datasketch` MinHash + LSH at Jaccard threshold **0.9**.
- Shingles: 3-gram words (after lowercasing + punctuation strip).
- `num_perm=128`; LSH bands/rows derived from threshold.
- Algorithm: O(N) — handles 50k posts comfortably on a laptop. (Pairwise `rapidfuzz.token_sort_ratio` is O(N²) — 50k posts ≈ 1.25B comparisons. Don't use it for the main pass; only for spot-checking.)
- Keep the earliest occurrence; route duplicates to `_rejected.jsonl` with reason `"near_duplicate_of:<post_id>"`.

Run dedup **after** anonymization so two posts that differ only in school name aren't treated as identical when underlying content is genuinely different.

---

## CLI

```
python -m preprocessing.run \
    --input  "C:/Users/Alex Evan/Documents/Research/scraper_project/data/" \
    --output "C:/Users/Alex Evan/Documents/Research/preprocessing/output/" \
    [--phases 1-10 | --phases 4 | --phases 2,3,8] \
    [--schools-config configs/schools.yaml] \
    [--limit 500] \
    [--dry-run] \
    [--seed 42]
```

`--phases` parses ranges and lists. Unselected phases pass-through. Each phase reads/writes intermediate JSONL in `output/_intermediate/phaseNN.jsonl` so partial reruns are cheap.

---

## Edge cases

| Case | Handling |
|---|---|
| Cross-university post (e.g. `"ADMU vs DLSU"`) | Both anonymized to `[Metro Manila] vs [Metro Manila]`. Kept in output. Logged in `_qc_report.cross_uni` for advisor review. |
| `"Manila"` / `"Baguio"` alone | Never replaced — too generic. |
| Quote/mention without ID intent (`"Ateneo daw ang sagot"`) | Replaced inline with `[Metro Manila]`. Anonymization commitment > rhetorical specificity. |
| Mascot collision (`Maroons` = UPD or UPB or PUP) | Tagged in `schools.yaml` as `ambiguous: true` (or simply not listed); replacement is **deletion** rather than a region tag. Same rule for any cross-region collision. |
| Generic mascots (`Lions`, `Eagles` outside `Blue Eagles`) | Drop, don't guess. |
| Region fallback when text is fully generic | Use `source` field (FW-01, SLU, etc.) to assign region only when no school markers were detected — never to override an explicit marker. |

---

## Dependencies (`preprocessing/requirements.txt`)

```
spacy==3.7.5
https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.7.1/en_core_web_lg-3.7.1-py3-none-any.whl
py3langid==0.3.0
datasketch==1.6.5
PyYAML==6.0.2
rapidfuzz==3.9.7
pytest==8.3.3
pytest-cov==5.0.0
```

Python ≥ 3.11 (matches scraper_project). All-local; **no cloud APIs** for NER or language detection.

---

## Verification (end-to-end test plan)

1. **Golden fixture**: `fixtures/golden_input.jsonl` with 20 hand-crafted posts — 2 per university covering hashtag/location/mascot/professor/Taglish + 2 cross-university posts + 2 dup/near-dup pairs + 2 edge cases (sub-10-char, pure-media). `golden_expected.json` declares the exact expected output per `post_id`. `tests/test_pipeline_e2e.py` asserts equality.
2. **Real-data smoke test**: `python -m preprocessing.run --input scraper_project/data --output output --limit 500`. Manually inspect 30 random output posts.
3. **No-leak assertion** (`tests/test_no_school_leaks.py`):
   ```python
   LEAK_PATTERNS = [
       r'\b(?:Ateneo|ADMU|Katipunan|Loyola Heights|Blue Eagle)\b',
       r'\b(?:UP\s*Diliman|UPD|Diliman|Sunken Garden)\b',
       r'\b(?:UPLB|Los\s*Ba(?:ñ|n)os|Makiling|Aggies)\b',
       r'\b(?:SLU|Saint Louis|Maryheights|Navigators)\b',
       r'\b(?:DLSU|La Salle|Taft|Green Archers)\b',
       r'\b(?:FEU|Morayta|Tamaraws)\b',
       r'\b(?:PUP|Sta\.\s*Mesa)\b',
       r'\b(?:LPU-?B|Lyceum)\b',
       r'\b(?:CSU|Cagayan State|Caraga State)\b',
       r'\b(?:UPB|UB|Governor Pack)\b',
       r'\b(?:BSU|La Trinidad|Mountaineers)\b',
       r'#\w*(?:FW|FreedomWall)\w*\d+',
   ]
   # For every post in every output file, assert text matches none.
   ```
4. **QC report sanity**: `_qc_report.json` must report `school_leak_count == 0`, language histogram with Taglish in 10–80% range, dedup rate <30% (anything higher signals an over-aggressive near-dup threshold).
5. **Manual audit**: `scripts/audit_sample.py` prints 50 random output posts; researcher signs off before declaring the dataset ready for downstream BERTopic.

---

## Top 5 risks & mitigations

1. **Acronym shadowing** — `UP` matching inside `UPLB` after partial substitution. **Mitigation:** strict ordering in §Anonymization order; per-acronym regression test that runs every acronym against every other acronym's strings.
2. **Encoding hell** — `Los Baños` (ñ), em-dashes, smart quotes from Facebook. **Mitigation:** `encoding="utf-8"` on read **and** write; `unicodedata.normalize("NFKC", text)` as the very first step in Phase 01.
3. **`HKT` timezone suffix breaks the existing parser** — `parse_absolute_timestamp` silently returns `None` on `"May 2, 2026 8:46:27 AM HKT"`, which would null every timestamp. **Mitigation:** Phase 08 strips `(HKT|PHT|GMT[+-]\d+|UTC[+-]\d+|PST)$` before delegating; unit test with the literal scraped string.
4. **Over-anonymization destroying meaning** — replacing every `UP` produces gibberish (`"[Metro Manila] late na ako"`). **Mitigation:** strict word-boundary lookbehind/lookahead on short acronyms; spot-check 50 sample replacements before bulk run.
5. **NER ordering** — running spaCy after lowercasing collapses recall by ~40%. **Mitigation:** Phase 04 (NER) executes **before** Phase 03 (case/punctuation normalization). Documented in `pipeline.py`.

---

## Discrepancies & open items to confirm with thesis advisor

1. **`scraper_project/config.py:TARGETS`** lists 10 entries (FW-01..FW-09 + SLU). The user's 12-school list adds DLSU and PUP, which have no scraper code yet. `schools.yaml` carries them with `scraper_code: null` — pipeline still handles their text patterns once those JSONLs land.
2. **UPLB code conflict**: user's prompt says `FW-02 = UPLB`; the scraper config says `FW-02 = UP Diliman` and `FW-04 = UPLB`. The schema below treats `FW-02 = UPD` (config-authoritative). **Verify with the actual Facebook URLs in `config.py` before running.**
3. **CSU disambiguation**: Cagayan State vs. Caraga State — the FW-06 Facebook page should be inspected to determine which.
4. **Mascot lists for low/medium-confidence schools** (LPU-B, BSU, UB, CSU) — verify against each school's official Facebook before final run.
5. **Stopword removal scope (Phase 06)**: per Section 3.3.5, particles are flagged here but removed downstream during BERTopic c-TF-IDF. Final cleaned-corpus output drops the `stopword_flags` field — it's an internal scaffold for the next pipeline stage, not a product of this one.
