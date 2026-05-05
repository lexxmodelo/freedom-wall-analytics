# Preprocessing Pipeline — Action Log

This file records every implementation step for the Freedom Wall preprocessing pipeline. Append-only; newest entries at the bottom.

Project: thesis on AI-Driven Topic Modeling and Multidimensional Sentiment Analysis of Student Discourse on Philippine University Freedom Walls.
Pipeline location: `C:\Users\Alex Evan\Documents\Research\preprocessing\` (sibling to `scraper_project/`).
Plan reference: [preprocessing_pipeline.md](../../docs/plans/preprocessing_pipeline.md)

---

## ACTION-001 — 2026-05-05 — Scaffold project structure

Created folder tree per plan §Folder layout:

```
preprocessing/
├── action_log.md            (this file)
├── preprocessing/           (Python package)
├── configs/
├── fixtures/
├── tests/
├── output/
└── scripts/
```

Verified before scaffolding:
- 5 of 12 universities are scraped: `FW-01=ADMU`, `FW-02=UPD`, `FW-03=FEU`, `FW-04=UPLB`, `SLU=SLU` (confirmed by inspecting the `post_url` and indexing-hashtag `#XXXFreedomWallNNN` of the first record in each JSONL).
- `FW-02 = UPD` (UP Diliman), not UPLB — the original prompt's note was a transcription slip; resolved per `scraper_project/config.py:TARGETS`.
- CSU = **Caraga State University** (confirmed by user); plan's `Cagayan State` alternative dropped.
- Most posts have `timestamp_raw: null` — adapted Phase 08 to emit `timestamp_unix: null` rather than reject posts when no parseable timestamp exists. QC report records the missing-timestamp count for advisor review.

Next: write `configs/schools.yaml` (12-school dictionary, CSU=Caraga, FW-02=UPD).

---

## ACTION-002 — 2026-05-05 — Implement configs

- `configs/schools.yaml` — 12-school dictionary. Confidence flags retained
  for advisor review (LPU-B/UB low; UPLB/CSU/UPB/BSU medium; rest high).
  CSU set to Caraga State per user confirmation.
  FW-02=UPD (per scraper_project/config.py:TARGETS, NOT UPLB).
  Includes `ambiguous_mascots` (Maroons/Lions/Eagles → drop, no region tag),
  `generic_location_allowlist` (Manila/Baguio/Cebu/Davao — never replaced),
  and `scraper_code_to_region` for source-based region fallback.
- `configs/stopwords_tagalog.txt` — pragmatic particles for phase06 flagging.
- `configs/stopwords_english.txt` — standard English closed-class words.
- `configs/tagalog_given_names.txt` — ~430-entry seed name list for phase04
  NER layer 2. Sourced from common Filipino given-name patterns; expand as
  the corpus reveals false negatives.

---

## ACTION-003 — 2026-05-05 — Implement Python package (phases 01-10)

Wrote 14 modules under `preprocessing/preprocessing/`:

- `__init__.py`, `logging_setup.py`, `io_utils.py`, `regex_lib.py`
- `schools.py` (YAML loader + replacement-table builder; 97 rules from 12 schools)
- `name_lists.py` (Tagalog given-name regex + department keyword/acronym patterns)
- `phase01_select.py` through `phase10_dedupe_qc.py` (all 10 phases)
- `pipeline.py` (orchestrator, runs phases in order: 01, 02, 04, 03, 05–10)
- `run.py` (CLI: `python -m preprocessing.run`, supports --limit / --phases / --verbose)

Runtime ordering deviates from numeric ordering: NER (phase04) runs BEFORE
noise reduction (phase03) so spaCy keeps the casing/punctuation it depends
on for entity recall. This is documented in `pipeline.py` and the plan.

---

## ACTION-004 — 2026-05-05 — Test scaffolding + golden fixture

- `fixtures/golden_input.jsonl` — 14 hand-crafted posts covering: hashtags
  (ADMU/UPD/FEU/UPLB/SLU), location markers (Katipunan, Sunken Garden,
  Maryheights, Los Baños, Morayta), mascots (Tamaraws, La Salle), professor
  reference (Sir Reyes), Filipino given name (Maria Cruz), pure-media,
  too-short, exact-duplicate pair, English-only, pure-Filipino, cross-uni
  comparison (ADMU vs DLSU).
- 7 test files (`tests/test_*.py`):
  - `test_phase02_anonymize.py` — 13 parametric replacement cases + 3 edge cases
  - `test_phase03_regex.py` — 7 regex-cleaning cases
  - `test_phase08_timestamps.py` — 4 timestamp parser cases incl. HKT suffix
  - `test_phase09_language.py` — 4 language detection cases
  - `test_pipeline_e2e.py` — full pipeline against golden fixture
  - `test_no_school_leaks.py` — hard assertion on output JSON files

---

## ACTION-005 — 2026-05-05 — Install deps, fix bugs, smoke test

Installed (Python 3.14): PyYAML, py3langid, datasketch, pytest. spaCy
deferred — no Python 3.14 wheels yet. Pipeline gracefully degrades without
spaCy (NER layers 2–4 still active via name list, professor regex, dept
keywords).

Bugs found and fixed:

1. **`scraper_project.utils.parse_absolute_timestamp` returns ISO string,
   not datetime** — phase08 was calling `.tzinfo` on a string. Added
   `_coerce_to_datetime` wrapper that handles either form.
2. **`Submitted:` mid-string not stripped** — original regex required
   line-start; relaxed to `\bSubmitted\s*:\s*` anywhere (just the prefix
   word; trailing signature falls through to phase04 NER).
3. **Acronym replacements were case-sensitive** — real posts use lowercase
   "admu", "slu", "uplb". Added `re.IGNORECASE` to the bare-acronym pattern.
4. **Standalone `#DLSU`/`#AnimoLaSalle` hashtags survived** — per-school
   regex only catches `#XXXFreedomWall...`. Added catch-all `#\w+` stripper
   in phase03 (runs AFTER per-school replacement so school-related hashtags
   become region tags first).
5. **Bare "Animo" missing from DLSU mascots** — added "Animo" and "Lady
   Archers" to schools.yaml.

Test results after fixes: **35 passed, 0 failed.**

---

## ACTION-006 — 2026-05-05 — Full corpus run (no limit)

Processed all 5 JSONL files end-to-end. Outputs in `output/`.

| Metric | Value |
|---|---|
| Posts in | 20,018 |
| Posts kept | 19,271 |
| Posts rejected | 37 |
| Exact duplicates dropped | 625 |
| Near duplicates dropped (Jaccard ≥ 0.9) | 85 |
| Cross-university posts | 97 |
| Region via source-code fallback | 91 |
| Posts missing timestamp | 19,268 |
| Runtime | ~42 seconds |

Region split: Metro Manila 11,284 · Luzon/Provincial 4,019 · Baguio/Benguet 3,968.
Language split: Filipino 6,944 · Taglish 6,524 · English 5,515 · Other 258 · Unknown 30.

**No-leak test passes on all three output files.**

Notes for advisor / next steps:

- **Almost all timestamps are missing** (19,268 of 19,271). The scraper
  populates `timestamp_iso: null` and `timestamp_raw: null` for the vast
  majority of posts. Downstream temporal analysis will need either a scraper
  fix or an alternative timestamp source (e.g. scraping the post page
  individually for the date stamp).
- **Other (258) and Unknown (30) language posts** — likely a mix of pure
  emoji/short-text posts and regional dialects. Currently kept in output;
  the dialect filter in phase09 only fires when py3langid explicitly
  classifies as ilo/pam/ceb/war/hil. May want to revisit thresholds after
  the advisor reviews a sample.
- **Source-code fallback region used for 91 posts** — these had zero school
  identifiers in their text. Routed by their JSONL's region (e.g. an
  FW-04.jsonl post with a generic complaint goes to Luzon/Provincial).
- **DLSU/PUP not yet scraped** (per scraper_project/config.py). Their
  schools.yaml entries are ready; pipeline will pick them up automatically
  once their JSONL files appear in `scraper_project/data/`.

When spaCy 3.x supports Python 3.14 (or via a 3.11 conda env), install
`spacy` + `python -m spacy download en_core_web_lg` to enable NER layer 1.
The pipeline will pick it up automatically — no code change needed.

---

## ACTION-007 — 2026-05-05 — Re-scrape with timestamps + spaCy on Python 3.14 + full re-run

**Trigger:** user provided a fresh scrape that includes timestamps and 7
schools (FW-01..FW-07). Asked to enable spaCy on Python 3.14 and rerun.

### Pre-flight checks on the new data

```
FW-01.jsonl  ts_iso: 2026-05-03T13:34:41+08:00  ts_raw: 1777786481
FW-02.jsonl  ts_iso: 2026-04-30T18:25:41+08:00  ts_raw: 1777544741
FW-03.jsonl  ts_iso: 2026-02-25T11:24:03+08:00  ts_raw: 1771989843
FW-04.jsonl  ts_iso: 2026-04-27T12:07:21+08:00  ts_raw: 1777262841
FW-05.jsonl  ts_iso: 2025-12-27T22:36:36+08:00  ts_raw: 1766846196
FW-06.jsonl  ts_iso: 2026-05-02T22:57:22+08:00  ts_raw: 1777733842
FW-07.jsonl  ts_iso: 2026-04-08T21:16:00+08:00  ts_raw: 1775654160
```

Two schema changes from prior batch:
1. `timestamp_raw` is now an integer Unix epoch (was a human-readable date
   string); `timestamp_iso` is an ISO-8601 string with TZ offset.
2. SLU is missing from this batch; FW-05/06/07 (LPU-B / CSU / UPB) added.

### Code changes

- **`phase08_timestamps.py::to_unix_pht`** — added a fast path that handles
  integer `timestamp_raw` directly (passes through if positive), plus a
  string-of-digits path for the stringified form. Tries
  `datetime.fromisoformat()` before falling back to the scraper's parser
  (handles the new `+08:00` offset cleanly).

### spaCy on Python 3.14

```
pip install spacy                              # 3.8.13
python -m spacy download en_core_web_lg        # 3.8.0 (400 MB)
```

Both worked. spaCy 3.8 ships Python 3.14 wheels (blis, thinc, cymem,
murmurhash all built for cp314). Verified with a quick smoke test:

```
>>> nlp = spacy.load('en_core_web_lg')
>>> [(e.text, e.label_) for e in nlp('Maria Cruz sent a love letter.').ents]
[('Maria Cruz', 'PERSON')]
```

NER layer 1 is now active in the pipeline; logged as enabled rather than
disabled.

### Output cleanup + full run

Cleared `output/*.json`, `output/*.jsonl`, `logs/*.log` before running.

Initial run surfaced two new leak categories not seen in the prior batch
(because LPU-B data wasn't there before):

1. **`LPUB` (no hyphen)** — real posts use the unhyphenated form. Added
   `LPUB`, `LPU`, `Lyceum` to LPU-B's `full_name_variations` in
   `configs/schools.yaml`.
2. **Bare `Lyceum`** — added (above).

After fixes, re-cleared output and ran again.

### Final results (full corpus, all 26,387 posts → 25,520 cleaned)

| Metric | Value |
|---|---|
| Posts in (across 7 files) | 26,387 |
| Kept after dedup + QC | 25,520 |
| Rejected (logged in `_rejected.jsonl`) | 135 |
| Exact duplicates dropped | 643 |
| Near duplicates dropped (Jaccard ≥ 0.9) | 89 |
| Cross-university posts (kept) | 132 |
| Region via source-code fallback | 5,388 |
| Posts with parsed timestamp | 25,520 (100%) |
| End-to-end runtime | ~8 minutes (with spaCy NER) |

**Region split:** Metro Manila 11,242 · Luzon/Provincial 11,934 · Baguio/Benguet 2,344
**Language split:** Filipino 9,060 · English 8,290 · Taglish 7,499 · Other 637 · Unknown 34

### Verification

- `pytest`: **35 / 35 pass** (32 unit + 3 no-leak assertions).
- All three regional output files contain **zero school-identifier leaks**.
- All 25,520 posts have `timestamp_unix` populated (was 19,268 missing in
  the prior batch — issue resolved by the rescrape).
- Source-code fallback region was used for 5,388 posts (~21%); these
  contained no explicit school markers, so were routed to their JSONL's
  region via the `scraper_code_to_region` map. This is expected behavior;
  flagged here for advisor awareness.

### Open items for advisor review

- **`Other` language posts (637)**: short / emoji-heavy / dialect content.
  Currently retained in output. Sample audit recommended.
- **DLSU and PUP still not scraped** (Metro Manila); `schools.yaml` entries
  ready and will be picked up automatically when their JSONLs land.
- **SLU not in this batch** (was in prior batch). When the next SLU scrape
  arrives, drop it into `scraper_project/data/` and rerun — no code change
  needed.

---

## ACTION-008 — 2026-05-05 — Ambiguity tier system + UB/PUP/Pirates fixes

**Trigger:** user spotted that case-insensitive acronym matching could
collide with common words (e.g. "UP" the school vs "up" the adverb), and
asked for a strategy plus an audit of similar issues.

### Audit results (raw input scan over all 26,387 posts)

Scanned for tokens with potential English/Filipino-word collisions:

| Token | Raw posts | Verdict |
|---|---|---|
| `UB` | 18 (across FW-02/05/07) | **Three different meanings**: University of Baguio, LPU-B colloquial use (likely "University of Batangas"), and basketball "Upper Box" tickets. **FW-09 itself has zero bare-UB mentions.** |
| `pup` lowercase | 7 | All refer to PUP the school in this corpus. No baby-dog false positives observed, but defensive case-sensitivity is cheap. |
| `Pirates` | 17 (FW-05) | Almost always `Pirates Cafe`/`Pirates Hall` — campus facility names, not the team mascot. |
| `Tamaraws/Tamaraw` | 130 (FW-03) | All FEU-self-identification ("Tamaraws of the South"). Safe to keep mapping. |
| `Diliman`/`Katipunan`/`Morayta`/`Butuan` | 155/61/17/103 | All school-context references in this corpus. Safe. |
| `Animo` | 7 | DLSU cheers; also one DLSU mention from an ADMU post. Safe. |
| `Mountaineers` | 3 | UPB student org. Cross-school within Baguio/Benguet (BSU listed but UPB context); same region, acceptable. |

### Strategy: 4-tier ambiguity classification

Documented in the schools.yaml header comment:

- **Tier A — Safe** (default): unique tokens, case-insensitive replace.
- **Tier B — Capital-only**: short acronyms whose lowercase form is a real
  word. Set `case_sensitive_acronym: true`.
- **Tier C — Ambiguous-drop**: token meaning is context-dependent. Add to
  top-level `ambiguous_mascots` (drop without region tag).
- **Tier D — Allowlist**: generic tokens that don't identify any school.
  Add to `generic_location_allowlist`.
- **Tier E — Skip-bare**: school's bare acronym collides across sources.
  Set `skip_bare_acronym: true`. School still anonymized via hashtag,
  full-name, and source-code fallback.

### Code changes

- **`preprocessing/schools.py::School`** — added `skip_bare_acronym` and
  `case_sensitive_acronym` boolean fields. Loader honors both.
- **`preprocessing/schools.py::build_replacement_table`** — bare-acronym
  pass now skips schools flagged with `skip_bare_acronym`, and omits
  `re.IGNORECASE` for schools flagged with `case_sensitive_acronym`.
- **`configs/schools.yaml`** — header comment documents the four tiers.
  Per-school changes:
  - `UB`: `skip_bare_acronym: true` (Tier E).
  - `PUP`: `case_sensitive_acronym: true` (Tier B).
  - `LPU-B`: removed `Pirates` from `mascot_cheer_terms`.
  - `ambiguous_mascots`: added `Pirates` (Tier C).
- **`tests/test_phase02_anonymize.py`** — three new tests:
  `test_skip_bare_acronym_ub_survives`,
  `test_case_sensitive_pup`,
  `test_pirates_now_ambiguous`.
- **`tests/test_no_school_leaks.py`** — adapted to policy:
  - `UB` removed from required-redacted patterns (Tier E intentionally
    allows it through). `University of Baguio` and `Cardinals` still
    required.
  - `PUP` split: uppercase `\bPUP\b` (case-sensitive, must be redacted)
    + lowercase forms of location markers (`Sta. Mesa`, `Mabini Campus`)
    case-insensitive (those are unambiguous and must always be redacted).

### Final results (full corpus rerun)

| Metric | Before tier fixes | After tier fixes |
|---|---|---|
| Total kept | 25,520 | 25,520 |
| Metro Manila | 11,242 | 11,244 |
| Luzon/Provincial | 11,934 | 11,944 |
| Baguio/Benguet | 2,344 | 2,332 |
| Cross-uni posts | 132 | 118 |

The shift (12 fewer Baguio/Benguet, 10 more Luzon/Provincial, 2 more Metro
Manila) is entirely explained by the UB Tier-E flag: posts from FW-05
that previously got mis-attributed to Baguio/Benguet via the bare-`UB`
match are now routed correctly via the source-code fallback to
Luzon/Provincial.

**Tests:** 38 passing (up from 35; +3 new tier-flag unit tests). All three
no-leak assertions pass on real output.

---

## ACTION-009 — 2026-05-05 — Architectural fix: source-only region routing + UPOU

**Trigger:** user spotted a UPD post (`aa6ece1d603284a9`) being routed to
Baguio/Benguet because its text mentioned "upb baby" (slang, not the school):

```json
{
  "post_id": "aa6ece1d603284a9",
  "text": "[Metro Manila] hi to my [Baguio/Benguet] baby unblock me pls",
  "region": "Baguio/Benguet"      // WRONG — post is from FW-02 (UPD, Metro Manila)
}
```

The pipeline conflated two concerns:
- **anonymization** (replacing school names in the text with regional tags)
- **region assignment** (which output bucket the post goes to)

The previous `assign_region` looked at `_phase02_regions` (regions matched
in the text) and only fell back to source-code when text had no matches.
For posts whose text mentioned a school from a different region, this
mis-routed the post — sometimes to the wrong region entirely (alphabetical
tiebreak on cross-uni posts).

User's correct framing: *"one Freedom Wall = one location"*. The post's
origin (the JSONL file) is the only authoritative region signal. School
names in the body are discourse content — they tell us what the post is
*about*, not where it's *from*.

### Code changes

- **`phase10_dedupe_qc.py::assign_region`** rewritten: always returns
  `cfg.scraper_code_to_region[post["_source_code"]]`. No text inspection.
  Cross-school text mentions don't change the post's region.
- **`phase10_dedupe_qc.py::finalize`** QC stats redesigned:
  - Removed: `cross_university_posts`, `region_via_source_fallback` (both
    described the old behavior).
  - Added: `text_mentions_no_school`, `text_mentions_own_region_only`,
    `text_mentions_other_region` (descriptive of discourse content; do
    NOT affect routing).
- **`configs/schools.yaml`** — added `UPOU` (UP Open University, Los Baños,
  Luzon/Provincial). 33 raw mentions across FW-02/FW-04 in the corpus,
  was previously not anonymized.

### Test updates

- **`fixtures/golden_input.jsonl`**: each post now carries an internal
  `_test_source_code` field declaring which JSONL it should be written
  to. Added two regression cases:
  - `g015`: the actual failing case — UPD post with "upb baby" must land
    in Metro Manila, not Baguio/Benguet.
  - `g016`: UPD post mentioning UPOU — verifies the new UPOU rule.
- **`tests/test_pipeline_e2e.py`** rewritten to split the fixture into
  per-source JSONL files (matching the new source-routing semantics) and
  assert source-based regions for representative posts.

### Verification

The exact post the user reported:

```
FOUND in metro_manila_posts.json
  region: Metro Manila
  text: [Metro Manila] hi to my [Baguio/Benguet] baby unblock me pls😅🙏
```

Reads naturally as the user's intended analytical surface: *"this Metro
Manila post says X about a [Baguio/Benguet] subject"*.

### Region-distribution shift after fix

| Region | Before architectural fix | After |
|---|---|---|
| Metro Manila | 11,244 | 11,275 (+31) |
| Luzon/Provincial | 11,944 | 11,921 (−23) |
| Baguio/Benguet | 2,332 | 2,324 (−8) |

31 posts moved into Metro Manila — these are FW-01/02/03 posts whose text
happened to mention non-MM schools (UPB, SLU, UPLB) and were previously
mis-routed away from their actual origin.

### New discourse-content metrics on the corpus

- `text_mentions_no_school`: 5,390 (21%) — posts with no recognized school
  identifier in body. Routed purely by source.
- `text_mentions_own_region_only`: 19,988 (78%) — posts mentioning only
  schools from their own region.
- `text_mentions_other_region`: 142 (0.6%) — true cross-region discourse;
  these are the most analytically interesting posts (students discussing
  schools across regions).

**Tests:** 38 passing. All no-leak assertions pass on real output.

---

## ACTION-010 — 2026-05-05 — Strip .ninja submission timestamps + indexing-hashtag header

**Trigger:** user observed three classes of metadata still appearing in the
cleaned text:

1. `#ADMUFreedomWall34401`-style indexing hashtag (the post's serial number
   on the .ninja submission platform).
2. `Submitted: October 6, 2025 11:46:33 PM UTC` footer — the .ninja platform
   submission timestamp, **not** the Facebook post time.
3. Standalone `Month Day, HH:MM:SS [AM/PM] UTC` strings without a
   "Submitted:" prefix (the scraper sometimes drops the prefix word).

### Audit (raw-input scan on all 26,387 posts)

- `Submitted:` lines: **6,386 matches** (~24% of posts).
- Standalone datetime stamps without "Submitted:": ~3,449 posts had datetime
  residue surviving in the previous run's cleaned output (13.5% of corpus).

### Code changes

- **`regex_lib.py::PATTERNS["submitted_prefix"]`** widened from
  `\bSubmitted\s*:\s*` to `\bSubmitted\s*:[^\n]*` — strips the full line
  through end-of-line/text, including the trailing date and any signature.
- **`regex_lib.py::PATTERNS["ninja_timestamp"]`** added — a strict regex
  that matches the .ninja format with the seconds field as the
  distinguishing signal:
  - Long form: `Month Day [, Year] HH:MM:SS [AM/PM] [TZ]`
  - ISO form: `YYYY-MM-DD HH:MM[:SS] [TZ]`
  Strict enough to avoid stripping casual date references like
  "see you March 15 at 8pm" (no seconds → no match).
- **`schools.py::build_replacement_table`** — indexing-hashtag rule now
  replaces with empty string, **not** the region tag. Rationale: the
  indexing hashtag is .ninja metadata (the post's serial number); the
  post's region is already captured in the top-level `region` output
  field via source-code routing, so a leading `[Metro Manila]` tag derived
  solely from the hashtag was redundant noise.
- **`phase03_noise_regex.py::clean_noise`** ordering: `submitted_prefix`
  runs before `ninja_timestamp` so the line strip claims its full extent
  before the standalone-stamp pass. Otherwise the second pass could leave
  a stranded "Submitted:" prefix.

### New unit tests (5 added)

- `test_strips_submitted_with_trailing_date`
- `test_strips_submitted_various_date_formats` (4 format variants)
- `test_strips_standalone_ninja_timestamp` (3 cases)
- `test_keeps_casual_date_without_seconds` (false-positive guard)
- Plus updates to existing tests in `test_phase02_anonymize.py` to reflect
  indexing-hashtag drop behavior.

### Verification on full corpus

```
0 of 25,418 posts still contain datetime/Submitted residue (0.00%)
```

The reported failing post `aa6ece1d603284a9` now reads:

```json
{
  "post_id": "aa6ece1d603284a9",
  "text": "hi to my [Baguio/Benguet] baby unblock me pls😅🙏",
  "region": "Metro Manila",
  "timestamp_unix": 1772876046
}
```

— cleanly matches the analytical surface: *"a Metro Manila post talking
about a [Baguio/Benguet] subject, posted at unix time T"*.

### Region-distribution shift

| Region | Before | After | Delta |
|---|---|---|---|
| Metro Manila | 11,275 | 11,269 | −6 |
| Luzon/Provincial | 11,921 | 11,862 | −59 |
| Baguio/Benguet | 2,324 | 2,287 | −37 |
| **Total kept** | **25,520** | **25,418** | **−102** |
| Total rejected | 135 | 194 | +59 |

102 fewer posts kept. These were posts whose entire content was metadata
(indexing hashtag + Submitted line, with no real body text); after
stripping they fell below the 10-char minimum quality gate. Routed to
`_rejected.jsonl` with reason `too_short`. Correct behavior — those posts
contained no analyzable discourse.

**Tests:** 42 passing (up from 38). All no-leak assertions still pass on
real output.

---

## ACTION-011 — 2026-05-05 — Add Mindanao region + Cebuano language preservation

**Trigger:** user pointed out that CSU is Caraga State University, located
in Butuan City, Caraga Region (Region XIII) — which is in **Mindanao**, not
Luzon. The previous mapping `CSU → Luzon/Provincial` was a geographic
error inherited from the original spec when CSU was assumed to be Cagayan
State (northern Luzon).

User's clarified intent: each region/location is its own analytical bucket
for cross-cultural comparison. So the right fix is to add a 4th region,
not to drop the data.

### Changes

1. **New region: Mindanao.**
   - `schools.yaml`: CSU moved from `Luzon/Provincial` → `Mindanao`. Added
     bare `Caraga` and `Agusan` as full-name variations / location markers
     (the previous dictionary missed these, leaving 5 leak posts).
   - `scraper_code_to_region`: `FW-06: Mindanao`.
   - `schools.py::REGION_TAGS`: added `Mindanao → [Mindanao]`.
   - `phase10_dedupe_qc.py::finalize`: bucket dict includes `Mindanao`.
   - `pipeline.py`: writes a 4th file `mindanao_posts.json`.

2. **Preserve regional Philippine languages as explicit labels.**
   - Previously `phase09_language.py` collapsed `ceb / ilo / pam / war / hil`
     to `Other` and the orchestrator dropped them as `regional_dialect`.
     Now: explicit labels (`Cebuano`, `Ilokano`, `Kapampangan`, `Waray`,
     `Hiligaynon`) and **kept in output** so cross-cultural comparison
     across regions can surface the linguistic differences.
   - Pipeline orchestrator: removed the dialect-rejection step entirely.
     QC report no longer carries `regional_dialect_dropped`.

3. **Cebuano detection heuristic added.**
   - py3langid misclassifies most FW-06 Cebuano posts as Tagalog (raw
     scan: 2,066 → `tl`, 1,630 → `en`, 0 → `ceb`). Added a `CEBUANO_FUNC`
     set (~80 distinguishing words: `naa, kay, og, dili, akong, imong,
     kinsa, asa, unsa, ngano, gani, gud, jud, bitaw, dayon, nga`, etc.)
     and a `ceb_ratio >= 0.05 AND > tl_ratio` rule that overrides the
     default Tagalog/English fallback.

### Test updates

- `test_no_school_leaks.py`: parametrization now covers all four regional
  output files; allow-list regex includes `[Mindanao]`. Added bare
  `Caraga` and `Agusan` to the leak patterns.
- `test_phase09_language.py`: added `test_cebuano_classified_explicitly`.
- `test_pipeline_e2e.py`: `_flatten` reads all four output files; added
  `g017` (CSU post with Caraga + Butuan markers) and `g018` (CSU post
  with Submitted: header) regression cases asserting Mindanao routing
  and content cleaning.
- `fixtures/golden_input.jsonl`: +2 fixtures (`g017`, `g018`).

### Final corpus distribution (full rerun, 26,387 → 25,417)

**Region:**
| Region | Posts |
|---|---|
| Metro Manila | 11,269 |
| Luzon/Provincial | 7,864 |
| Mindanao | 3,997 |
| Baguio/Benguet | 2,287 |

**Language (cross-region):**
| Lang | Posts |
|---|---|
| Filipino | 8,245 |
| English | 7,768 |
| Taglish | 7,495 |
| Cebuano | 1,300 |
| Other | 417 |
| Unknown | 192 |

**Language histogram per region** (the analytical surface the user wants
for cross-cultural comparison):

| Region | Top languages |
|---|---|
| Metro Manila | English 4,917 · Taglish 3,089 · Filipino 2,854 |
| Luzon/Provincial | Filipino 3,743 · Taglish 2,505 · English 1,340 |
| Baguio/Benguet | Filipino 923 · Taglish 801 · English 475 |
| Mindanao | Taglish 1,100 · **Cebuano 1,096** · English 1,036 · Filipino 725 |

The Mindanao corpus is the only region where Cebuano is a major language
(27% of posts) — exactly the cross-cultural signal the user wanted to
preserve.

**Tests:** 44 passing. All four no-leak assertions pass on real output.

---

## ACTION-012 — 2026-05-05 — Multi-language stopword bundle for downstream BERTopic

**Trigger:** user asked how non-Taglish/English words are handled. Audit
revealed a real gap in phase06: only Tagalog particles were being flagged
for downstream BERTopic c-TF-IDF stopword removal. English stopwords
existed as a file but were never loaded. Cebuano (1,300 posts) and
Ilokano (potential future scrapes) had no stopword coverage at all.

This would have polluted downstream BERTopic topic descriptors on the
Mindanao subset — "kay og naa students" instead of capturing the actual
content theme.

### New stopword files

- **`configs/stopwords_cebuano.txt`** (~95 entries) — pronouns, particles,
  wh-words, negation, common verbs/adverbs, the highly distinctive linker
  `nga`. Curated from the `CEBUANO_FUNC` set in phase09 plus pragmatic
  additions (`gani, gud, jud, bitaw, dayon, sus, char`, etc.).
- **`configs/stopwords_ilokano.txt`** (~60 entries, defensive starter) —
  articles (`ti, dagiti, iti`), pronouns (`siak, sika, isuna, dakami`),
  particles (`ket, ngem, no, ta, laeng, met, manen`), wh-words, negation,
  common copulas. Conservative; advisor or native speaker can extend.

### Code changes

- **`phase06_stopwords.py`** rewritten:
  - Now auto-discovers all `stopwords_<language>.txt` files in a config
    directory rather than taking a single Tagalog-only path.
  - `_stopword_flags` field is now structured as `{language: {token: count}}`
    so downstream BERTopic consumers can apply language-specific stopword
    sets per-region. (Field is still dropped from final output, but the
    files in `configs/` are the persistent artifact.)
  - English stopwords now actually loaded (was a pre-existing dead file).
- **`pipeline.py::PipelineConfig`** — replaced `tagalog_stopwords_path`
  with `stopwords_dir`.
- **`run.py`** — replaced `--tagalog-stopwords` flag with `--stopwords-dir`
  (auto-discovers `stopwords_*.txt` files).
- **`tests/test_phase06_stopwords.py`** added (5 tests):
  auto-discovery; per-language flagging for Tagalog and Cebuano;
  separation guarantee (Cebuano-specific markers don't appear under
  the Tagalog count).

### How downstream BERTopic should consume

The four `configs/stopwords_*.txt` files are now the persistent contract.
When running BERTopic on a region's output, the consumer combines the
relevant bundles:

| Region output | Recommended stopword bundles |
|---|---|
| `metro_manila_posts.json` | `tagalog + english` |
| `luzon_provincial_posts.json` | `tagalog + english` |
| `baguio_benguet_posts.json` | `tagalog + english + ilokano` |
| `mindanao_posts.json` | `tagalog + english + cebuano` |

(Cross-language posts still get caught by the union, since e.g.
Mindanao Taglish posts still benefit from Tagalog stopwords.)

### Verification

Real-corpus check on three Cebuano-classified Mindanao posts:

```
[07507ae1] {'cebuano': 5, 'english': 4, 'ilokano': 2}
[ba534092] {'cebuano': 4, 'english': 1, 'ilokano': 2, 'tagalog': 1}
[6532f1e4] {'cebuano': 12, 'english': 12, 'ilokano': 1, 'tagalog': 1}
```

Cebuano particles (`kay, og, naa, akong, dayon, nga`) caught by the new
bundle would otherwise have leaked into BERTopic descriptors. The small
Ilokano counts are shared-particle overlap (`ti, na, ko`) and are
expected; they don't matter as long as the consumer applies the
language-appropriate bundle for each region.

**Tests:** 49 passing (up from 44; +5 new in `test_phase06_stopwords.py`).
All no-leak assertions still pass on real output.

---

## ACTION-013 — 2026-05-05 — Switch to PH admin-region labels (NCR / CAR / CALABARZON / CARAGA)

**Trigger:** user questioned whether the ad-hoc 4-region scheme (Metro
Manila / Luzon-Provincial / Baguio-Benguet / Mindanao) was methodologically
sound versus standard Philippine administrative regions. After discussion,
agreed to switch to PSA admin labels for citability, future-proofing, and
better cultural-linguistic correlation.

### Mapping (current scraped data)

| Old label | New label | Schools | Posts |
|---|---|---|---|
| Metro Manila | **NCR** | ADMU, UPD, FEU | 11,276 |
| Luzon/Provincial | **CALABARZON** | UPLB, LPU-B | 7,867 |
| Baguio/Benguet | **CAR** | UPB, BSU, UB, SLU | 13,933 |
| Mindanao | **CARAGA** | CSU | 3,998 |

(Note: this run also picked up the new SLU/BSU/UB scrapes — total corpus
grew from 26,387 to 38,389 raw posts; 37,074 kept after dedup/QC.)

### Code changes

- **`schools.py`**:
  - `REGION_TAGS` redesigned to enumerate all 17 PH admin regions
    explicitly (NCR, CAR, Region I–XIII, CALABARZON, MIMAROPA, CARAGA,
    BARMM). Future scrapes drop in without code changes.
  - Added `REGION_FILENAME_SLUG` map (region label → output-filename
    slug) for all 17 regions.
- **`schools.yaml`**:
  - All 13 schools' `region` field updated to admin labels.
  - `scraper_code_to_region` map updated with explicit comments noting
    each school's actual location (e.g. `FW-04: CALABARZON   # UPLB —
    Los Baños, Laguna`).
  - Header documentation expanded with the 17-region naming convention.
- **`phase02_anonymize_school.py::_TAG_REPEAT`** — regex now built from
  `REGION_TAGS` keys so it covers all 17 regions, not just the four
  currently active.
- **`phase10_dedupe_qc.py::finalize`** — bucket dict now pre-allocates
  one slot per known PH admin region; empty buckets filtered at write
  time.
- **`pipeline.py`** — output writer is data-driven: only generates
  `<slug>_posts.json` for regions that have posts. New scrapes that land
  in a previously-empty region (e.g. Bicol) automatically produce a new
  output file with no code change.

### Critical bug found and fixed mid-rollout: NER mangling region tags

After the relabel, the no-leak test surfaced a case where `[CARAGA]` was
appearing in output without enclosing brackets — `[REDACTED_NAME]CARAGA]`
on post `a174d9487b3795ec`.

Root cause: spaCy's PERSON entity recognition was spanning into our
phase02 region tags. For a raw text like `Jollibee Ampayon nga gitaagan`,
phase02 produced `Jollibee [CARAGA] nga gitaagan`; spaCy then identified
`Jollibee [` as part of a PERSON entity span (4 tokens with the opening
bracket pulled in), replaced with `[REDACTED_NAME]`, leaving `CARAGA]`
orphaned.

Fix in `phase04_ner.py`: mask all `[REGION]` tags with single-token
sentinels (`REGIONTAG{n}MASK`) before running spaCy NER, restore them
after. spaCy treats the sentinels as opaque OOV tokens and doesn't tag
them. Tested by manually inspecting the previously-mangled post —
output is now clean.

### Tests updated

- All `[Metro Manila]` / `[Luzon/Provincial]` / `[Baguio/Benguet]` /
  `[Mindanao]` literals in test files replaced with `[NCR]` /
  `[CALABARZON]` / `[CAR]` / `[CARAGA]`.
- No-leak parametrization now covers `ncr_posts.json`,
  `calabarzon_posts.json`, `car_posts.json`, `caraga_posts.json`.
- `test_no_school_leaks.py::ALLOWLIST` regex covers all 17 admin
  regions (so future Bicol/Visayas/etc. scrapes won't false-positive).

### Final corpus distribution

**Region:**
| Region | Posts | Schools active |
|---|---|---|
| CAR | 13,933 | UPB, BSU, UB, SLU |
| NCR | 11,276 | ADMU, UPD, FEU |
| CALABARZON | 7,867 | UPLB, LPU-B |
| CARAGA | 3,998 | CSU |

**Language (cross-region):** Filipino 13,244 · Taglish 11,890 ·
English 9,577 · Cebuano 1,472 · Other 583 · Unknown 308.

### Limitation flagged for thesis advisor

**Intra-region heterogeneity is invisible at the region label.** NCR
lumps Ateneo (elite private) with PUP (state university with very
different demographic) into one bucket. CAR lumps Baguio's urban-
multilingual schools with potential future scrapes from rural Mountain
Province / Ifugao / Kalinga. The pipeline preserves the source-school
identity in `_source_code` (which stays internal — not in final output)
so a downstream within-region stratification is recoverable, but the
cleaned corpus alone supports only region-level analysis. Recommend
documenting this as a methodological limitation in Section 3.3 of the
thesis writeup.

**Tests:** 49 passing. All four no-leak assertions pass on real output.

---

## ACTION-014 — 2026-05-05 — Switch output to per-school batches for downstream Topic Labelling

**Trigger:** user requested per-Freedom-Wall output files (FW-01 through
FW-09 + SLU) instead of region-aggregated files. Stated rationale: each
school's corpus is the BATCH UNIT for downstream BERTopic + topic
labelling (Section 3.5 of the methodology). The cross-regional
aggregation will happen at analysis time, not at preprocessing time.

### Methodology check (Research.md, Sections 3.4–3.6)

- Section 3.4 describes BERTopic running on "the corpus"; it does not
  prescribe the corpus-unit (combined vs. per-school).
- Section 3.6.1 describes the system as a "Scheduled Batch Pipeline".
- Per-school batching is consistent with the stated cross-cultural
  comparison goal: BERTopic on each school surfaces school-specific
  topic landscapes that can be compared across regions, whereas BERTopic
  on the combined corpus would average cultural signal away.

Conclusion: per-school output is feasible and methodologically supported.

### Code changes

- **`phase10_dedupe_qc.py::finalize`** rewritten to bucket by
  `_source_code` instead of `region`. Each post still carries its
  `region` field, so downstream cross-regional aggregation is
  `pd.concat([files...]).groupby('region')` — single source of truth,
  no duplication.
- **Output schema gained one field**: `source_code` (e.g., `FW-01`,
  `SLU`). Already an anonymized identifier (no school name leak); kept
  inline so that flattened/merged datasets retain batch attribution
  without re-deriving from filename.
- **`pipeline.py`** writer simplified: one file per source code with
  filename `{source_code}_cleaned.json`. Empty buckets skipped.
- **`test_pipeline_e2e.py`** schema assertion updated to expect 7 fields
  (`source_code` added). New per-school batching invariant: each output
  file contains posts from exactly one source code, and the filename
  matches that source code.
- **`test_no_school_leaks.py`** parametrization is now data-driven via
  `output_dir.glob("*_cleaned.json")` — automatically covers all
  per-school files generated by any given run.

### Final output (after full rerun)

```
output/
├── FW-01_cleaned.json   (ADMU)         3,735 posts
├── FW-02_cleaned.json   (UPD)          3,578
├── FW-03_cleaned.json   (FEU)          3,963
├── FW-04_cleaned.json   (UPLB)         3,955
├── FW-05_cleaned.json   (LPU-B)        3,912
├── FW-06_cleaned.json   (CSU/Caraga)   3,998
├── FW-07_cleaned.json   (UPB)          2,287
├── FW-08_cleaned.json   (BSU)          3,791
├── FW-09_cleaned.json   (UB)           3,991
├── SLU_cleaned.json     (SLU)          3,864
├── _qc_report.json
└── _rejected.jsonl
```

Total kept: 37,074 / 38,389 raw (260 rejected for too-short / pure-media
/ no-region-assignable; ~1k dropped via global exact + near dedup).

Each post's `region` field still preserved for trivial cross-regional
aggregation:

```python
import json, pandas as pd
from pathlib import Path
df = pd.concat([
    pd.DataFrame(json.loads(p.read_text(encoding='utf-8')))
    for p in Path("output").glob("*_cleaned.json")
])
df.groupby("region").size()
# CAR           13933
# NCR           11276
# CALABARZON     7867
# CARAGA         3998
```

### Verification

The reported failing post `aa6ece1d603284a9` now appears in
`FW-02_cleaned.json` with the full per-school + region schema:

```json
{
  "post_id": "aa6ece1d603284a9",
  "source_code": "FW-02",
  "text": "hi to my [CAR] baby unblock me pls😅🙏",
  "engagement": {"reactions": 1, "comments": 0, "shares": 1},
  "timestamp_unix": 1772876046,
  "region": "NCR",
  "language_detected": "English"
}
```

**Tests:** 55 passing (10 new auto-discovered no-leak assertions across
all 10 per-school files). Full run completed in ~9 minutes including
spaCy NER on all 38k posts.
