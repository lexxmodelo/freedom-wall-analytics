# Plan: Add `desktop_graphql_httpx` Strategy — Bypass the Browser Memory Cliff

## Context

**Problem.** The desktop scraper freezes at ~1700 posts on the owner's laptop, while a co-author's desktop reaches 2000+. The cliff is documented in [action_log.md:384](C:\Users\Alex Evan\Documents\Research\scraper_project\action_log.md) as a per-machine V8 heap / Chrome RSS ceiling: each scroll accumulates DOM nodes, GraphQL response payloads, and React objects until Windows starts paging and the renderer GC-thrashes. The freeze-proof architecture (700 MB heap-pressure restart, 500-scroll cycle cap, DOM pruning, periodic CDP GC) mitigates but cannot eliminate the hardware limit. Apify and Bright Data don't hit this because they don't run a desktop browser at all — they replay GraphQL calls directly with HTTP clients.

**Approach.** Add a fourth strategy that does the same: launch Chrome briefly to harvest the persisted-query tokens (`fb_dtsg`, `lsd`, `jazoest`, `doc_id`, initial cursor), close it, then drive `/api/graphql/` cursor pagination with `httpx`. RAM usage drops from ~2 GB to ~50 MB. No DOM, no scroll, no freeze cliff. The same researcher's laptop should reach the 4000-post target.

**Outcome.** A new `desktop_graphql_httpx` strategy added FIRST in the strategies list. It runs to completion if Facebook accepts the replay; otherwise the existing `desktop` Playwright strategy runs as fallback (per the existing strategy loop at `scraper.py:815–830`). Token expiry handled both proactively (refresh every 45 min) and reactively (on response error).

---

## Phase 1 — Proof of concept (validate before integrating)

**File:** `scripts/test_graphql_httpx.py` *(new)*

Standalone script (~150 LOC) that proves the technique works against current Facebook before any production code changes.

1. Load cookies via the existing `_load_cookies` pattern ([scraper.py:515–553](C:\Users\Alex Evan\Documents\Research\scraper_project\scraper.py)).
2. Launch a single Playwright Chrome page with cookies + localStorage restored.
3. Register `page.on("request", ...)` to capture every `POST` to `/api/graphql/`. Snapshot:
   - Request `body` (form-encoded) → parse out `fb_dtsg`, `lsd`, `jazoest`, `doc_id`, `fb_api_req_friendly_name`, `variables`.
   - Request `headers` (User-Agent, X-FB-LSD, X-ASBD-ID, etc.).
   - Cookies via `context.cookies()`.
4. Navigate to `https://www.facebook.com/p/SLU-Freedom-Wall-61563510362403/` (FW-10 / SLU is the owner's own page — safest test target).
5. Scroll twice (`page.mouse.wheel`) to trigger a *pagination* request, not just the initial feed query. The pagination request is the one we replay.
6. Stop capturing once the pagination request is in hand. Close Chrome.
7. Build an `httpx.Client` with the captured cookies + headers, then loop:
   - POST to `https://www.facebook.com/api/graphql/` with the captured form payload, replacing only the `cursor` in `variables` with the latest `end_cursor` from the previous response.
   - Parse the response body using `_GraphQLPostExtractor._iter_json_chunks` and `_walk_for_stories` directly (they're already `@staticmethod`, no refactor).
   - Extract `end_cursor` via `_walk_for_cursors`.
   - Sleep 2–5 s (use `random_sleep` from `utils.py`).
8. Stop after 50 posts or 10 iterations. Log: time elapsed, posts collected, RSS measured via `psutil.Process().memory_info().rss`.
9. **Success criterion:** ≥ 50 unique posts collected, RSS stays under 200 MB, total time under 60 s.

If Facebook rejects the replay (HTTP 400, GraphQL `errors[]` field, or empty edges), the script logs the failure shape and exits 1. We then know whether the issue is `fb_dtsg` (rotated mid-session), `doc_id` (whitelisted), or anti-bot signals (need extra headers like `sec-fetch-*`).

**Files to read but not modify in PoC phase:**
- [scraper.py:40–296](C:\Users\Alex Evan\Documents\Research\scraper_project\scraper.py) — `_GraphQLPostExtractor` (reuse the static parsers).
- [scraper.py:515–575](C:\Users\Alex Evan\Documents\Research\scraper_project\scraper.py) — `_load_cookies`, `_restore_session_state`.
- [scraper.py:1576–1701](C:\Users\Alex Evan\Documents\Research\scraper_project\scraper.py) — `_cookies_to_httpx`, mbasic httpx client setup. Reuse the pattern.
- `utils.py` — `post_hash`, `normalize_timestamp`, `random_sleep`.

---

## Phase 2 — Production integration

Only proceed once Phase 1 passes. Changes:

### 2a. Config additions — [config.py](C:\Users\Alex Evan\Documents\Research\scraper_project\config.py)

Append to `ScraperConfig`:

```python
# --- GraphQL httpx strategy ---
graphql_httpx_request_delay_min: float = 2.0
graphql_httpx_request_delay_max: float = 5.0
graphql_httpx_token_refresh_minutes: int = 45     # proactive refresh
graphql_httpx_max_consecutive_errors: int = 5     # bail to fallback strategy
graphql_httpx_harvest_scrolls: int = 2            # scrolls during harvest to trigger pagination request
graphql_httpx_harvest_timeout_seconds: int = 30
```

Update `strategies` default list (line 135–139) to put the new strategy FIRST:

```python
strategies: list = field(default_factory=lambda: [
    "desktop_graphql_httpx",   # NEW: token harvest + httpx replay (no browser memory cliff)
    "desktop",                 # FALLBACK: full Playwright path (current working strategy)
    "basic_mobile_httpx",
    "basic_mobile",
])
```

### 2b. New module — `graphql_httpx.py` *(new file)*

Keeps the new logic out of the already-2300-line `scraper.py`. Exposes:

- `harvest_tokens(scraper, cfg, code, url) -> TokenBundle | None`
  Launches Chrome via the existing `_launch_context` helper, navigates, scrolls `cfg.graphql_httpx_harvest_scrolls` times, captures the first pagination POST to `/api/graphql/`, closes Chrome. Returns a dataclass `TokenBundle` with `cookies`, `headers`, `form_payload_template`, `variables_template`, `initial_cursor`, `harvested_at`.

- `paginate(scraper, cfg, code, tokens, posts, seen_hashes) -> tuple[list[dict], str]`
  The httpx loop. Returns `(posts, stop_reason)` where `stop_reason ∈ {"target_reached", "end_of_feed", "token_expired", "max_errors", "killed"}`. Reuses `_GraphQLPostExtractor._iter_json_chunks`, `_walk_for_stories`, `_walk_for_cursors` directly — they're static.
  - Detects token expiry by inspecting response: HTTP 401/403, GraphQL `errors[].message` containing "session" or "fb_dtsg", or a response with no edges + no error (silent failure).
  - On expiry → return `("token_expired", ...)`. The caller orchestrates re-harvest.
  - Per-iteration: build form body by mutating `variables.cursor`, POST, parse, dedupe via `seen_hashes` (shared set, same contract as `_GraphQLPostExtractor._seen`), append, checkpoint every `cfg.checkpoint_interval` posts via the existing `scraper._checkpoint_save`.

- `should_refresh(tokens, cfg) -> bool`
  Returns `True` if `time.monotonic() - tokens.harvested_at > cfg.graphql_httpx_token_refresh_minutes * 60`.

### 2c. Strategy dispatch — [scraper.py:862–870](C:\Users\Alex Evan\Documents\Research\scraper_project\scraper.py)

Add an `elif` branch in `_run_strategy`:

```python
elif strategy == "desktop_graphql_httpx":
    return self._desktop_graphql_httpx_strategy(url, code)
```

### 2d. New scraper method — `_desktop_graphql_httpx_strategy(self, url, code)`

Lives in `scraper.py`. Thin orchestrator:

1. Initialize `posts = self._checkpoint_load(code)`, `seen_hashes = {post_hash(p["text"]) for p in posts}` (mirrors the desktop strategy's resume logic at lines 936–951).
2. `tokens = graphql_httpx.harvest_tokens(self, self.cfg, code, url)`. If `None`, return `posts` (forces the strategy loop to fall through to `"desktop"`).
3. Loop until target reached or `consecutive_errors ≥ cfg.graphql_httpx_max_consecutive_errors`:
   - If `graphql_httpx.should_refresh(tokens, self.cfg)`: re-harvest. On harvest failure, break.
   - `posts, stop_reason = graphql_httpx.paginate(self, self.cfg, code, tokens, posts, seen_hashes)`.
   - If `stop_reason == "token_expired"`: re-harvest, continue loop.
   - If `stop_reason == "end_of_feed"`: break — this is success, the page is exhausted.
   - If `stop_reason == "target_reached"`: break.
   - If `stop_reason == "max_errors"`: break — fallback to `"desktop"`.
4. Final `_checkpoint_save(posts, code)`. Return `posts`.

### 2e. Reuse, don't rewrite

- **Cookies:** `self._cookies` is already populated in `__init__`. Pass straight to `httpx.Cookies` via the existing `_cookies_to_httpx` helper at [scraper.py:1576–1590](C:\Users\Alex Evan\Documents\Research\scraper_project\scraper.py).
- **Checkpointing:** `self._checkpoint_save(posts, code)` and `self._checkpoint_load(code)` ([scraper.py:~1481–1562](C:\Users\Alex Evan\Documents\Research\scraper_project\scraper.py)). Same JSONL format — researchers' downstream pipeline doesn't change.
- **Dedupe:** `post_hash(text)` from `utils.py`. The `seen_hashes` set is identical in shape to the one the desktop strategy uses, so resuming a httpx run from a desktop checkpoint (or vice versa) Just Works.
- **Post dict shape:** Already produced correctly by `_GraphQLPostExtractor._walk_for_stories` ([scraper.py:230–238](C:\Users\Alex Evan\Documents\Research\scraper_project\scraper.py)). `source: "graphql"` is preserved — useful for analyzing later which strategy collected which post.
- **Browser launch:** `harvest_tokens` calls `scraper._launch_context(...)` (existing helper) so all anti-detection flags, persistent profile logic, and Chrome args carry over identically. No duplication.

### 2f. CLI / logging

No new CLI flag needed — the strategies list governs everything. Log lines should clearly distinguish the new strategy in tqdm postfix and structured logs:

```
[SLU] desktop_graphql_httpx: harvested tokens (doc_id=12345, cursor=AbCd...)
[SLU] desktop_graphql_httpx: 50 posts, RSS=85MB, last_cursor=XyZ1...
[SLU] desktop_graphql_httpx: token refresh (45min elapsed)
[SLU] desktop_graphql_httpx: end-of-feed at 3847 posts
```

---

## Phase 3 — Verification

### 3a. PoC verification (Phase 1 gate)

```
cd C:\Users\Alex Evan\Documents\Research\scraper_project
python scripts/test_graphql_httpx.py --target SLU --max-posts 50
```

Pass criteria:
- Exit code 0
- ≥ 50 unique posts in stdout summary
- Peak RSS < 200 MB (logged via `psutil`)
- Wall time < 60 s
- No HTTP errors, no GraphQL `errors[]` in responses

### 3b. Integration verification (Phase 2 gate)

Run a short integration test against SLU first (smallest, owner-controlled page):

```
python -m scraper_project.scraper --code SLU --target-posts 200 --strategies desktop_graphql_httpx
```

Pass criteria:
- 200 posts collected without browser launching after the harvest phase
- `data/SLU.jsonl` matches the schema produced by the desktop strategy (sample 5 lines, diff key sets)
- Resume test: kill mid-run, restart — confirms `_checkpoint_load` correctly seeds `seen_hashes` and the loop picks up where it left off without duplicate writes
- Token-refresh test: lower `graphql_httpx_token_refresh_minutes` to 1, run 200 posts, confirm logs show ≥ 1 re-harvest and no posts lost across the boundary

### 3c. Cliff test (the real point)

```
python -m scraper_project.scraper --code SLU --target-posts 4000
```

Expected: completes to 4000 posts (or end-of-feed) without freezing. RSS stays under 250 MB throughout. If `desktop_graphql_httpx` fails partway, the strategy loop falls through to `desktop` and it should still complete via the existing pipeline — so the change is non-regressive.

### 3d. Regression test (don't break existing strategy)

```
python -m scraper_project.scraper --code SLU --target-posts 200 --strategies desktop
```

Confirms the existing desktop strategy still runs correctly when explicitly selected.

---

## Files modified / created

| Path | Change |
|---|---|
| `scripts/test_graphql_httpx.py` | **NEW** — Phase 1 standalone PoC (~150 LOC) |
| `graphql_httpx.py` | **NEW** — `harvest_tokens`, `paginate`, `should_refresh`, `TokenBundle` dataclass (~250 LOC) |
| `config.py` | Add 6 new fields, update `strategies` default list (~10 LOC) |
| `scraper.py` | Add `_desktop_graphql_httpx_strategy` method + dispatch elif (~50 LOC). No edits to `_GraphQLPostExtractor` — its static parsers are reused as-is. |
| `action_log.md` | Document as ACTION-032 |

## Non-goals

- Not refactoring `_GraphQLPostExtractor` — its static parsers work as-is.
- Not changing the JSONL schema or post dict shape — downstream analysis pipeline stays untouched.
- Not removing the `desktop` strategy — it remains the safety net.
- Not altering the existing `mbasic_*` strategies — they remain as cheap probes.
- No mobile proxies, no stealth-plugin upgrades — orthogonal to the memory-cliff fix.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Facebook rejects replayed `doc_id` (persisted-query whitelist enforces hash match against `variables`) | Phase 1 PoC catches this before integration. If it fires, fall back to capturing the FULL pagination request including `server_timestamps: true` and `fb_api_caller_class` — Crawlee blog technique forces the server to return the unhashed query. |
| `fb_dtsg` rotates faster than 45 min | Reactive refresh on error catches this. The 45 min knob can be tuned down. |
| Cloudflare WAF flags httpx as bot despite valid tokens | Add `sec-fetch-mode`, `sec-fetch-site`, `sec-fetch-dest`, `priority`, `accept-language` headers captured verbatim from the harvested request. |
| Resume-from-checkpoint behaves differently between strategies | Verified by integration test 3b — `seen_hashes` and the JSONL writer use identical contracts. |
| New strategy succeeds but collects fewer posts than `desktop` would have | Strategy loop already handles this: if returned posts < `min_posts_threshold`, the next strategy runs. No code change needed. |
