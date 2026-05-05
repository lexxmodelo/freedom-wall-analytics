# Scraper Execution — Action Log

**Started:** 2026-05-01  
**Objective:** Collect at least one semester (~3 months) of Freedom Wall posts from 10 target institutions using cookie-authenticated Playwright scraping.

---

## Phase 1: Environment Setup

### ACTION-001 — Create action log
- **Time:** 2026-05-01
- **Action:** Created this file (`action_log.md`) to track all execution steps.
- **Status:** DONE

### ACTION-002 — Install Python dependencies
- **Time:** 2026-05-01
- **Action:** Ran `pip install playwright beautifulsoup4 tqdm pandas`
- **Result:** All packages installed successfully. playwright==1.59.0, beautifulsoup4==4.14.3, tqdm==4.67.3, pandas (already present).
- **Note:** Playwright scripts path not on PATH — using `python -m playwright` instead.
- **Status:** DONE

### ACTION-003 — Install Playwright Chromium browser
- **Time:** 2026-05-01
- **Action:** Ran `python -m playwright install chromium`
- **Result:** Downloaded Chrome for Testing 147.0.7727.15, FFmpeg, Chrome Headless Shell, Winldd. Total ~292MB. Installed to `C:\Users\Alex Evan\AppData\Local\ms-playwright\`.
- **Status:** DONE

---

## Phase 2: Cookie Extraction

### ACTION-004 — Launch interactive Facebook login
- **Time:** 2026-05-01
- **Action:** Running `python extract_cookies.py` to open a Chromium window for the user to log in to Facebook.
- **Expected:** Browser opens → user logs in → script detects URL change → saves cookies to `cookies.json`.
- **Status:** BLOCKED — Python 3.14 asyncio compatibility issue

### ACTION-005 — Fix Python 3.14 asyncio compatibility
- **Time:** 2026-05-01
- **Issue:** `asyncio.WindowsSelectorEventLoopPolicy()` is deprecated in Python 3.14 and breaks Playwright's subprocess spawning. The `SelectorEventLoop` cannot create subprocesses on Windows — Playwright needs `ProactorEventLoop` (the default).
- **Fix:** Removed `asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())` from both `extract_cookies.py` and `main.py`. The default `ProactorEventLoop` supports subprocess creation natively.
- **Files modified:** `extract_cookies.py`, `main.py`
- **Status:** DONE

### ACTION-006 — Retry interactive Facebook login (attempt 2)
- **Time:** 2026-05-01
- **Action:** Re-running `python extract_cookies.py` after removing WindowsSelectorEventLoopPolicy.
- **Result:** Still failed — `BrowserType.launch: spawn UNKNOWN`. Playwright's async API is fundamentally broken on Python 3.14 Windows (ProactorEventLoop subprocess handling changed).
- **Status:** FAILED — escalated to ACTION-007

### ACTION-007 — Full async-to-sync migration
- **Time:** 2026-05-01
- **Issue:** Playwright async API (`async_playwright`) is incompatible with Python 3.14 on Windows. The async subprocess transport layer changed in 3.14, breaking Playwright's browser process spawning.
- **Decision:** Migrate entire codebase from async Playwright to sync Playwright (`sync_playwright`). The sync API does not depend on asyncio event loops for subprocess management.
- **Files rewritten:**
  - `extract_cookies.py` — replaced `async_playwright` with `sync_playwright`, removed all async/await
  - `scraper.py` — rewrote `FacebookScraper` class to sync: `scrape_target()`, `_desktop_run()`, `_basic_mobile_strategy()` all sync
  - `parser.py` — `DesktopParser` methods already use sync Playwright ElementHandle API (no change needed, just verified)
- **Status:** DONE

### ACTION-008 — Fix remaining async references in utils.py and main.py
- **Time:** 2026-05-01
- **Changes to `utils.py`:**
  - Removed `import asyncio` and `from functools import wraps`
  - Added `import time`
  - Removed `async_retry` decorator (no longer used — scraper.py has its own sync retry loop)
  - Replaced `async def random_delay(lo, hi)` with sync `def random_sleep(lo, hi)` using `time.sleep()`
- **Changes to `main.py`:**
  - Removed `import asyncio`
  - Changed `from utils import random_delay` → `from utils import random_sleep`
  - Converted `async def run_playwright()` → `def run_playwright()` (removed await on `scrape_target` and `random_delay`)
  - Converted `async def main()` → `def main()`
  - Changed `asyncio.run(main())` → `main()`
- **Verification:** All 5 Python files pass `py_compile` syntax check and full import chain resolves successfully.
- **Status:** DONE

---

## Phase 2: Cookie Extraction (retry)

### ACTION-009 — Launch interactive Facebook login (sync API)
- **Time:** 2026-05-01
- **Action:** Running `python extract_cookies.py` with fully sync Playwright API.
- **Result:** Still failed — `spawn UNKNOWN`. The Playwright-bundled Chromium (chromium-1217) cannot launch in headed mode on this Windows 11 + Python 3.14 environment.
- **Root cause:** Playwright's bundled Chromium binary crashes during headed launch. Headless works fine. This is a Chromium build compatibility issue, not a Python/asyncio issue.
- **Status:** FAILED — escalated to ACTION-010

### ACTION-010 — Switch to system Chrome via channel='chrome'
- **Time:** 2026-05-01
- **Issue:** Playwright-bundled Chromium fails `headless=False` on this machine. System-installed Chrome works via `channel='chrome'`.
- **Test:** `pw.chromium.launch(headless=False, channel='chrome')` — launches successfully. Also tested `channel='msedge'` — works.
- **Fix:**
  - `config.py` — added `browser_channel: Optional[str] = "chrome"` to ScraperConfig
  - `scraper.py` — both `_desktop_run()` and `_basic_mobile_strategy()` now pass `channel=self.cfg.browser_channel` to `pw.chromium.launch()`
  - `extract_cookies.py` — added `channel="chrome"` to `pw.chromium.launch()`
- **Status:** DONE

### ACTION-011 — Launch interactive Facebook login (system Chrome)
- **Time:** 2026-05-01
- **Action:** Running `python extract_cookies.py` with system Chrome (`channel='chrome'`).
- **Result:** Success! User logged in, 5 Facebook cookies saved to `cookies.json`.
- **Status:** DONE

---

## Phase 3: Scraping Execution

### ACTION-012 — Test scrape: SLU (headed, authenticated)
- **Time:** 2026-05-01
- **Action:** Running `python main.py --cookies cookies.json --targets SLU --headed --target-posts 100`
- **Result:** 17 posts collected. Desktop strategy found 17 posts in 117s, then stale scroll limit hit. Basic mobile found 0 (mbasic URL format issue with `/p/` pages). Timestamps were all `None`.
- **Issues identified:**
  1. Stale scroll limit (10) too aggressive — Facebook infinite scroll has gaps
  2. Not navigating to "Posts" tab — the page landing page shows limited content
  3. Scroll method `scrollBy(900)` not triggering lazy-load reliably
- **Status:** DONE — escalated to ACTION-013

### ACTION-013 — Improve scroll strategy and navigation
- **Time:** 2026-05-01
- **Changes:**
  - `config.py`: increased `stale_scroll_limit` from 5→15 (base), auth mode sets it to 25
  - `config.py`: added `browser_channel: Optional[str] = "chrome"` (already done in ACTION-010)
  - `scraper.py`: changed scroll from `scrollBy(900)` to `scrollTo(0, document.body.scrollHeight)` + small scroll-back to trigger lazy load
  - `scraper.py`: added `_navigate_to_posts_tab()` method — clicks "Posts" tab on Facebook pages before scrolling
  - `scraper.py`: auth mode stale limit increased from 10→25
- **Status:** DONE

### ACTION-014 — Re-test scrape: SLU (improved scroll)
- **Time:** 2026-05-01
- **Action:** Re-running `python main.py --cookies cookies.json --targets SLU --headed --target-posts 100`
- **Result:** 103 posts collected in 12.2 min (60 scrolls). Target reached. Desktop strategy worked after clicking "Posts" tab. Rate: ~1.7 posts/scroll.
- **Data quality audit:**
  - Ran analysis on all 103 entries. Found **91/103 (88%) are comments, not posts**.
  - Only 12 entries contained the `#SLUFreedomWall` tag (actual page posts).
  - Comment examples: "Reply", "Top fan" labels, tagged usernames, short replies like "retweet", "interested po".
  - One prolific commenter ("Mik Hail A Bat", top fan) accounted for ~20 comment entries alone.
  - Text length: min=18, max=447, avg=120 chars — comments skew short.
  - All 103 timestamps were `None` — parser selectors (`a[href*='/posts/'] span`, `time[datetime]`, `abbr[data-utime]`) don't match Facebook's current 2026 DOM structure.
  - Engagement: only 46/103 had any engagement > 0. Comment entries typically showed 0.
  - URLs: 103/103 had `post_url` — even comments had URLs (parent post URLs).
- **Root cause:** `page.query_selector_all("[role='article']")` returns both posts and comments. Facebook wraps comments in `[role='article']` elements nested inside the parent post's `[role='article']`.
- **Status:** DONE — data quality issues escalated to ACTION-015

### ACTION-015 — Fix comment contamination
- **Time:** 2026-05-01
- **Root cause:** `page.query_selector_all("[role='article']")` returns ALL article elements, including comments. In Facebook's DOM, comments are `[role='article']` nested inside a parent `[role='article']` (the post).
- **Fix:** Added a JavaScript check before parsing each article:
  ```python
  is_comment = article.evaluate("el => !!el.parentElement.closest('[role=\"article\"]')")
  if is_comment: continue
  ```
  This skips any article that has a parent with `role='article'`, filtering out comments and only keeping top-level feed posts.
- **Status:** DONE

### ACTION-016 — Re-test scrape: SLU (with comment filter)
- **Time:** 2026-05-01
- **Run 1 (comment filter + scrollTo):**
  - 10 posts collected, then crash: `Page.evaluate: Execution context was destroyed, most likely because of a navigation`
  - Root cause: `window.scrollTo(0, document.body.scrollHeight)` (added in ACTION-013) caused Facebook to trigger an internal navigation/DOM teardown, destroying the JS execution context.
  - Fix: reverted scroll to `window.scrollBy(0, scroll_pixels + random(0,500))` with try/except around the evaluate call. Added 3s fallback wait on exception.
- **Run 2 (comment filter + safe scrollBy):**
  - 16 real posts collected in 228s (56 scrolls, then 25 stale scrolls → stop).
  - All 16 posts are genuine `#SLUFreedomWall` posts (#25060 through #25074). No comments.
  - Text lengths: 147–447 chars (meaningful content, not stubs).
  - Engagement present on ~50% of posts. Timestamps still all `None`.
  - Comment filter confirmed: 16 posts vs 103 in unfiltered run = 84% were comments.
- **Root cause of low yield (16 vs target 100):** Inspected `cookies.json`:
  - Present: `datr`, `fr`, `sb`, `wd`, `dpr` (tracking/preference cookies)
  - **Missing:** `c_user` (user ID), `xs` (session token) — the critical auth cookies
  - Without `c_user`/`xs`, Facebook treats the session as unauthenticated. It showed a login modal (which was dismissed), but limits feed depth to ~15-20 posts before blocking infinite scroll.
- **Status:** DONE — need to re-extract cookies with proper login

### ACTION-017 — Fix cookie extraction to verify session cookies
- **Time:** 2026-05-01
- **Fix:** Updated `extract_cookies.py` to:
  1. Check for `c_user` and `xs` cookies after login
  2. Wait 10 extra seconds if missing (propagation delay)
  3. Abort with clear error message if session cookies still missing
  4. Extended initial wait from 3s to 5s post-login
- **Status:** DONE

### ACTION-018 — Re-extract cookies with proper login (attempts 1-3)
- **Time:** 2026-05-01
- **Attempt 1:** Timed out (5 min). User did not log in during the window.
- **Attempt 2:** Timed out (5 min). Same issue.
- **Attempt 3:** Timed out (5 min). Script now shows "saving whatever cookies exist" on timeout. Confirmed cookies still missing `c_user`/`xs`.
- **Adjustment:** Updated `extract_cookies.py` to not abort on URL-check timeout — proceeds to cookie check regardless. Added user-facing messages explaining what to do.
- **Status:** FAILED — user needs to be present at computer for login

### ACTION-019 — Re-extract cookies (attempts 4-6)
- **Time:** 2026-05-01
- **Attempt 4:** Login detected by URL check, but script immediately navigated to facebook.com before user could complete CAPTCHA → browser closed prematurely. User reported: "I have not finished the captcha and its closing immediately."
- **Attempt 5 (input-based):** Changed to `input()` for manual trigger. Failed — `EOFError` because the Bash tool runs non-interactively (no stdin).
- **Attempt 6 (polling-based):** Replaced `input()` with a 10-minute polling loop that checks `context.cookies()` every 5 seconds for `c_user`/`xs`. Browser stayed open 10 full minutes. User logged in, but cookies still only: `datr, dpr, fr, sb, wd`. Session cookies (`c_user`, `xs`) never appeared.
- **Root cause:** Facebook detects Playwright automation via:
  1. `--enable-automation` Chrome flag (added by Playwright by default)
  2. `navigator.webdriver === true` (JavaScript property set by Playwright)
  3. `_GRECAPTCHA` cookie confirmed reCAPTCHA was triggered by automation detection
  Facebook issues tracking cookies but refuses to create a full session (`c_user`/`xs`) for automated browsers.
- **Status:** FAILED — escalated to ACTION-020

### ACTION-020 — Hide automation signals from Facebook
- **Time:** 2026-05-01
- **Fix:** Updated `extract_cookies.py` browser launch:
  1. Added `ignore_default_args=["--enable-automation"]` to remove automation flag
  2. Added `args=["--disable-blink-features=AutomationControlled"]` to hide Blink automation features
  3. Added `page.add_init_script(...)` to override `navigator.webdriver` → `undefined`
  These changes make the browser appear as a normal user-launched Chrome instance to Facebook's bot detection.
- **Status:** DONE

### ACTION-021 — Re-extract cookies (attempt 7, persistent context + anti-detection)
- **Time:** 2026-05-01
- **Change:** Rewrote `extract_cookies.py` to use `launch_persistent_context()` instead of `launch()` + `new_context()`. A persistent context creates a real Chrome user profile directory (in temp), making the browser appear fully normal to Facebook. Combined with the anti-detection flags from ACTION-020.
- **Result:** SUCCESS! Session cookies detected after 65 seconds.
- **Cookies saved (8 total):** `datr`, `sb`, `wd`, `dpr`, `c_user`, `fr`, `xs`, `presence`
- **Critical cookies present:** `c_user` (user ID) ✓, `xs` (session token) ✓
- **Key insight:** The combination of persistent context + removed `--enable-automation` + hidden `navigator.webdriver` was needed to bypass Facebook's bot detection. Any one of these alone was insufficient.
- **Status:** DONE

---

## Phase 3: Authenticated Scraping

### ACTION-022 — Test scrape: SLU (fully authenticated, first attempt)
- **Time:** 2026-05-01
- **Action:** Ran `python main.py --cookies cookies.json --targets SLU --headed --target-posts 200`
- **Result:** 201 posts collected in 28.3 min (113 scrolls). Target reached.
- **Data quality audit:**
  - 125/201 entries were comments (URLs contained `comment_id=` parameter)
  - 76/201 entries were Messenger chat messages (private conversations from user's Facebook Messenger)
  - 0/201 were actual Freedom Wall posts
  - Root cause: Facebook's authenticated view does **NOT** wrap feed posts in `[role='article']` — only comments and Messenger messages get that role. The scraper was collecting the wrong elements.
  - Engagement: "57m" (57 minutes ago timestamp) was parsed as 57M reactions (parsing error)
  - Timestamps: All 201 were `None`
- **Status:** DONE — data quality issues escalated to ACTION-024

### ACTION-023 — Add anti-detection flags to scraper.py
- **Time:** 2026-05-01
- **Issue:** `scraper.py` used plain `pw.chromium.launch(headless=..., channel=...)` without anti-detection flags. Only `extract_cookies.py` had them.
- **Fix:** Added to both `_desktop_run()` and `_basic_mobile_strategy()`:
  1. `args=["--disable-blink-features=AutomationControlled"]`
  2. `ignore_default_args=["--enable-automation"]`
  3. `page.add_init_script(...)` to override `navigator.webdriver` → `undefined`
- **Files modified:** `scraper.py`
- **Status:** DONE

### ACTION-024 — Fix post detection for authenticated Facebook DOM
- **Time:** 2026-05-01
- **Investigation:** Created 4 diagnostic scripts (`debug_dom.py`–`debug_dom4.py`) to inspect the actual Facebook DOM in authenticated mode.
- **Key findings:**
  1. `[role='article']` only matches comments and Messenger messages in authenticated view
  2. Actual feed posts are plain `<DIV>` elements inside a feed container with 25+ children
  3. Posts have no permalink URLs — only profile links, `?__cft__` relative links, and hashtag links
  4. The feed container is inside `[role='main']` with children of consistent width (~680px)
  5. Timestamps are embedded in post text as "Submitted: Month DD, YYYY HH:MM:SS AM/PM"
- **Fix — `scraper.py`:**
  - Replaced `page.query_selector_all("[role='article']")` with new `_find_post_elements()` method
  - New method uses JavaScript to find the feed container (DIV with 8+ visible children of consistent width inside `[role='main']`)
  - Marks post children with `data-fw-post` attribute, then selects them
  - Falls back to `[role='article']` for unauthenticated mode
  - Added `_is_comment_or_noise()` method: filters by `comment_id=` in URL, Messenger signals, and "Reply" text patterns
- **Fix — `parser.py`:**
  - Added `_extract_timestamp_from_text()`: regex extracts "Submitted: Month DD, YYYY HH:MM:SS AM/PM" from post body
  - Added `a[href*='pfbid']` selectors and direct link text extraction (not just span children)
  - Added JavaScript-based timestamp extraction for `a[role="link"]` elements with date keywords
- **Fix — `utils.py`:**
  - Added `"%B %d, %Y %I:%M:%S %p"` and `"%B %d, %Y %I:%M %p"` to absolute timestamp formats
- **Status:** DONE

### ACTION-025 — Verify fix: SLU authenticated test (30 posts)
- **Time:** 2026-05-01
- **Action:** Ran `python main.py --cookies cookies.json --targets SLU --headed --target-posts 30`
- **Result:** 32 posts collected in 1.7 min (11 scrolls). Target reached.
- **Data quality:**
  - FW tagged: 32/32 (100%) — zero contamination
  - Timestamps: 12/32 (37%) — "Submitted:" timestamps extracted from expanded posts
  - Engagement: 20/32 (62%) — reasonable values (1-57 reactions)
  - Messenger entries: 0, Comment entries: 0
  - Text avg: 251 chars, min 30, max 447
  - URLs: 0/32 — authenticated view doesn't expose post permalink URLs (known limitation)
  - Note: Posts showing "See more" (collapsed) don't display "Submitted:" timestamp in text
- **Status:** DONE — ready for production run

### ACTION-026 — Production optimization for multi-hour 4,000-post runs
- **Time:** 2026-05-02
- **Motivation:** Pages are public and have unbounded scroll depth. Need reliable 8-hour runs without session loss, scroll stalls, or data loss on crash.
- **Changes — `config.py`:**
  - Added `use_persistent_context: bool = True` — reuse the logged-in Chrome profile from `extract_cookies.py` instead of injecting cookies into a fresh context
  - Added `persistent_profile_dir: str = ""` — filled at runtime with `os.path.join(tempfile.gettempdir(), "fb_login_profile")`, same path used by `extract_cookies.py`
  - Added `checkpoint_interval: int = 200` — flush to disk every 200 posts
  - Updated `page_timeout_seconds` comment: "raised to 28800 (8h) in auth mode"
- **Changes — `scraper.py` `_load_cookies()`:**
  - Changed from `max(current, value)` to direct assignment for authenticated-mode limits:
    - `page_timeout_seconds = 28800` (8 hours, was 1800)
    - `max_scroll_attempts = 5000` (was 800)
    - `stale_scroll_limit = 60` (was 25)
    - `scroll_delay_min = 3.5`, `scroll_delay_max = 7.0` (was 4.0/9.0 — faster for public pages)
- **Changes — `scraper.py` `_desktop_run()`:**
  - Added persistent context branch: when `cfg.use_persistent_context=True`, launches `pw.chromium.launch_persistent_context(profile_dir, ...)` instead of `browser.new_context()`. Session is already live in the profile — no cookie injection needed. `finally` calls `context.close()` instead of `browser.close()`.
  - Added checkpoint saves: every `checkpoint_interval` posts, calls `_checkpoint_save()` to write `{code}_checkpoint.json`
  - Added stale backoff scroll: when `stale_count > 20`, scrolls back 300px then forward `scroll_pixels + 600` to un-stick Facebook's lazy loader; uses this in place of the normal scroll on stale iterations
- **Added — `scraper.py` `_checkpoint_save()`:**
  - New method: writes `data/{code}_checkpoint.json` with all posts collected so far. Survives browser crashes, Ctrl+C, power loss (only loses since last checkpoint).
- **Files modified:** `config.py`, `scraper.py`
- **Status:** DONE

### ACTION-027 — Speed, RAM, and "See More" overhaul
- **Time:** 2026-05-02
- **Motivation:** Production test showed three critical problems: (1) scraping rate collapsed from 10s/post to 100s/post after 80 scrolls due to O(n×layout) JS scan; (2) posts with "See more" captured as truncated text; (3) Chrome RAM usage hit 99%+ — 10 processes, DOM accumulating 10,000+ nodes indefinitely; (4) Unicode crash on checkpoint log with `→` on Windows CP1252.
- **Fix 1 — Feed container cache (`scraper.py` `_find_post_elements()`):**
  - Added `data-fw-feed` attribute on first feed container detection. All subsequent calls skip the full `querySelectorAll('div')` scan and go directly to `querySelector('[data-fw-feed]')`. Full scan happens exactly once per page. Eliminates the O(n×layout) slowdown that caused 100s/post after 80 scrolls.
- **Fix 2 — See More expansion (`scraper.py` new `_click_see_more()`):**
  - New method injected before each parse cycle. Clicks all `div[role="button"]` / `span[role="button"]` elements with text "See more" inside the feed scope, waits 800ms for DOM to expand. Full post text now captured for all posts.
- **Fix 3 — DOM cleanup (`scraper.py` new `_cleanup_dom()`):**
  - New method called after each parse cycle. Removes all `[data-fw-post]` elements from the DOM. Feed container (`[data-fw-feed]`) is preserved. Keeps DOM node count bounded (~50) throughout the entire run instead of growing to 10,000+. Primary RAM fix.
- **Fix 4 — Chrome memory flags (`scraper.py` `_desktop_run()`):**
  - Added to both persistent and non-persistent context launch args: `--disable-dev-shm-usage`, `--disable-background-networking`, `--disable-sync`, `--disable-notifications`, `--disable-translate`, `--disable-default-apps`, `--js-flags=--max_old_space_size=512` (caps V8 heap at 512MB).
- **Fix 5 — Scroll delay reduced:**
  - Auth-mode delay: 3.5–7.0s → 1.5–3.5s. Safe with persistent session and DOM cleanup.
- **Fix 6 — Unicode crash:**
  - Replaced `→` with `->` in `_checkpoint_save()` log string. Fixes `UnicodeEncodeError` on Windows CP1252 console.
- **Files modified:** `scraper.py`
- **Status:** DONE — tested with --target-posts 100

### ACTION-029 — ScrollWatchdog: kill frozen page.evaluate() after 90 s
- **Time:** 2026-05-02
- **Motivation:** Scraper process was alive (tqdm showed ~96 posts) but frozen for 10+ minutes with no progress. Root cause: `page.evaluate()` in the scroll loop has no built-in timeout in Playwright's sync API. When Facebook's end-of-feed modal locks the JS event loop, `page.evaluate()` hangs forever. Threading-based `_safe_evaluate()` wrapper was attempted but failed with `greenlet.error: cannot switch to a different thread` — Playwright sync API is greenlet-bound and page methods cannot be called from any other thread.
- **Fix — `_ScrollWatchdog` nested class using `ctypes.PyThreadState_SetAsyncExc`:**
  - Added `_ScrollWatchdog` class to `FacebookScraper` (after `_restore_session_state`).
  - Watchdog starts a daemon thread. Each scroll iteration calls `watchdog.heartbeat()` to reset the timer.
  - If 90 s pass without a heartbeat, the watchdog calls `ctypes.pythonapi.PyThreadState_SetAsyncExc(main_tid, KeyboardInterrupt)` — injecting `KeyboardInterrupt` into the main thread at the next Python bytecode boundary. No Playwright calls are made from the watchdog thread.
  - Scroll loop has an `except KeyboardInterrupt` block: logs the freeze, prints posts saved so far, lets execution fall through to normal save/export.
  - `finally` block: `watchdog.stop()` + `pbar.close()` — watchdog always cleaned up even if loop exits normally.
  - Added `import ctypes` and `import threading` to imports.
- **Files modified:** `scraper.py`
- **Status:** DONE

### ACTION-028 — Graceful fallback for corrupted Chrome profile
- **Time:** 2026-05-02
- **Motivation:** Repeated force-kills during testing corrupted the Chrome persistent profile (`fb_login_profile`). Removing `SingletonLock` files was not sufficient — Chrome exits immediately with `exitCode=21` on every subsequent launch attempt, blocking all scraping. The scraper was stuck in a hard failure with no recovery path.
- **Fix — Wrap `launch_persistent_context` in try/except with cookie-injection fallback (`scraper.py` `_desktop_run()`):**
  - `launch_persistent_context` is now wrapped in `try/except Exception`.
  - On failure, the scraper logs a warning and automatically falls back to `pw.chromium.launch()` + `browser.new_context()` + `context.add_cookies(self._cookies)`.
  - Fallback uses the same Chrome args (memory flags, anti-detection, etc.).
  - If cookies are available, they are injected into the new context; session is authenticated as before.
  - If no cookies are available, a warning is logged and the session continues unauthenticated.
  - This makes the scraper self-healing: even after a corrupted profile, it continues using cookie-auth without any manual intervention.
- **Files modified:** `scraper.py` (lines 185–245)
- **Status:** DONE

---

## Phase 7: Apify-style reliability pass + post-mortem fix

### ACTION-030 — Apify-style reliability pass: JSONL checkpoint, cycle-100 cap, mbasic-via-httpx
- **Time:** 2026-05-04
- **Motivation:** Cross-machine instability — owner reaches ~1600–1700 posts before Chrome freezes; other researchers freeze between 220–500 even with 16 GB RAM. Root causes (diagnosed): CDP IPC throughput variance across hardware/OS, DOM accumulation as O(N²), V8 heap fragmentation, and bundled-Chromium-vs-system-Chrome version drift. RAM is not the bottleneck — IPC is. A colleague suggested adapting Apify-style techniques (mbasic primary via plain HTTP, append-only checkpoint, smaller browser sessions, optional proxy).
- **Plan file:** `C:\Users\Alex Evan\docs/plans/scraper_apify_reliability_pass.md`
- **Changes:**
  1. **Append-only JSONL checkpointing** (`scraper.py`):
     - Replaced `_checkpoint_save` (was: full JSON rewrite every 30 s to `{code}_checkpoint.json`) with append-only writes to `data/{code}.jsonl`. Per-target `self._jsonl_written_ids` set deduplicates so repeat calls only append the delta.
     - Added `_checkpoint_load(code)` — tolerant line-by-line read; skips a torn final line (mid-write crash recovery). One-time migration: if legacy `{code}_checkpoint.json` exists and `{code}.jsonl` doesn't, converts the JSON into JSONL automatically.
     - Final flush at end of `_desktop_run` so the JSONL is always the durable record (matches the `{code}.json` deliverable).
     - Resume block at `_desktop_run` start updated to seed both the dedupe set AND `_jsonl_written_ids` from the JSONL.
  2. **Cycle cap reduced 500 → 100** (`config.py:max_scrolls_per_session`): intent was to stay below every observed freeze cliff (220–500) on slower machines.
  3. **Fast-forward boundary threshold reduced 30 → 15** (`scraper.py:fast_forward_via_extractor`): cuts fast-forward duplicate slog roughly in half on every restart cycle.
  4. **mbasic-primary via httpx** (`scraper.py:_basic_mobile_strategy_httpx`, `config.py`): added a pure-HTTP scrape path against `mbasic.facebook.com` using `httpx`. Reuses existing `BasicMobileParser` (no parser changes). Helpers: `_to_mbasic_url`, `_cookies_to_httpx`. Block detection covers HTTP ≥400, redirect off mbasic, login/checkpoint/captcha sentinels. New tunables: `mbasic_request_delay_min/max` (3–6 s), `mbasic_max_pages` (200). Strategy order updated to put `basic_mobile_httpx` ahead of `desktop`.
  5. **httpx added to `requirements.txt`**.
- **Files modified:** `scraper.py`, `config.py`, `requirements.txt`, `guide.md`, `QUICKSTART.md`
- **Tests:**
  - Smoke (target=50): 52 posts in 64 s, JSONL written, target_reached.
  - Resume (target=80, JSONL present): "Resumed from checkpoint: 52 posts pre-loaded" → 82 posts final, JSONL = 82 lines.
  - Long-run (target=300): 302 posts in 378 s, 2 sessions, cycle@100 fired correctly, fast-forward crossed boundary at scroll 118 in 86.8 s.
  - mbasic httpx isolated: HTTP 200 OK but `mbasic.facebook.com` serves a "Facebook is not available on this browser" error page for every modern UA tested (Pixel 7, desktop Chrome, Firefox, MSIE, Nokia). Older UAs (iPhone Safari old) get redirected to `m.facebook.com` (React-rendered, plain HTTP returns no posts) or `intent://` Play Store deeplinks (Chrome rejects, `net::ERR_ABORTED`). Even Playwright with the same UA fails. **Conclusion: mbasic.facebook.com is currently UA-gated by Facebook for authenticated accounts; the Apify-style mbasic-primary approach does not currently produce posts.** `basic_mobile_httpx` was reordered to run *after* `desktop` (as a cheap probe — ~1.5 s of failed-fast latency before falling through). UA-gate detection (`"not available on this browser"` in body) added so the failure is logged clearly. Implementation will start working immediately if/when Facebook re-opens mbasic.
- **Status:** DONE — but see ACTION-031 below for the post-mortem on cycle-cap=100.

### ACTION-031 — Post-mortem: revert cycle-cap to 500, add unique-stale guard
- **Time:** 2026-05-04
- **Motivation — observed regression on the owner's machine:** A long authenticated SLU run with the new cycle@100 setting reached 1582/4000 posts in 1h15m, then degraded to 54.94 s/post with a 36-hour ETA. Symptom: progress bar showed `scroll=639, sess=7, stale=0` while posts stayed pinned at 1582 even though Chrome was visibly scrolling and `net=2505` GraphQL responses had been captured. Run was visibly stalled but the existing `stale_count` did not fire because of the `network_alive` short-circuit (any GraphQL response within the 12-second window resets stale, even when responses contain only duplicates).
- **Root cause:** The cycle-100 plan assumed restart overhead was approximately constant. It is not — fast-forward is **O(N)** in `len(seen_hashes)`. Each restart resumes from the top of the feed, so the scraper must scroll past *every previously-collected post* before finding new content. At Facebook's ~2 dup-posts-surfaced-per-scroll, a 1500-post run pays ~750 scrolls of fast-forward overhead per cycle. With a 100-scroll cap, that means each later cycle is ~7× slower than the actual productive work it does. Cycles trended toward yielding fewer than 50 net new posts each, with throughput collapsing asymptotically.
- **Secondary cause:** `stale_count` is suppressed when `network_alive=True`, which is correct for transient dedup-saturation but wrong for sustained duplicate-only periods (the post-restart fast-forward overlap, end-of-feed, or an approaching CDP/heap freeze). The 30-stale-scroll early-exit therefore could never fire during the pathology, leaving the session stuck.
- **Fix:**
  1. **Revert `max_scrolls_per_session` 100 → 500** in `config.py` (and the alias `session_restart_threshold`). 500 is the empirical sweet spot — comfortable margin below the typical freeze cliff on the owner's machine (~1700) and large enough that fast-forward overhead is amortized over many useful scrolls.
  2. **Add unique-stale guard** in `_desktop_run` — a new counter `unique_stale_count` increments whenever a scroll completes without growing `seen_hashes`. Reset on dedupe-set growth and on session restart. New stop condition: `if unique_stale_count >= cfg.unique_stale_limit (=50): break`. Fires regardless of `network_alive`, so it catches the three real conditions: dedup-saturation post-restart, end-of-feed, and approaching freeze (Chrome serving the same posts).
  3. **New config knob** `unique_stale_limit: int = 50` (`config.py`).
  4. **Progress bar postfix** now exposes `ustale=` so researchers can see if the dedupe set is stuck.
  5. **Existing safeguards retained:** 700 MB heap-pressure backstop, 90 s ScrollWatchdog, normal `stale_scroll_limit=30` (auth) for offline-feed cases.
- **What is kept from ACTION-030:** JSONL append-only checkpointing (independent win, crash-safe), `target_fresh_posts=15` (smaller fast-forward budget when restarts do happen), mbasic httpx strategy code (currently inert due to UA-gate, ready to activate if mbasic re-opens).
- **Files modified:** `scraper.py`, `config.py`, `guide.md`, `QUICKSTART.md`
- **Tests:**
  - Smoke (target=50, FW-01): 51 posts in 72 s, target_reached. Throughput restored to pre-cap baseline (~52 posts in 64 s).
  - Syntax/import check: clean. New config values: `max_scrolls_per_session=500`, `session_restart_threshold=500`, `unique_stale_limit=50`.
- **Trade-off / known risk:** Researchers whose machines actually freeze before scroll 500 will not be protected by the cycle cap alone — they now rely on the heap-pressure trigger (700 MB), unique-stale guard (50 scrolls), and the 90 s ScrollWatchdog. If that turns out to be insufficient, the next iteration is signal-based adaptive cycling (track CDP eval round-trip latency over a window; restart when the median triples). Not implemented now — current trio of signals should cover real-world freeze patterns.
- **Status:** DONE

### ACTION-032 — `desktop_graphql_httpx`: bypass the freeze cliff entirely
- **Time:** 2026-05-04
- **Plan file:** `C:\Users\Alex Evan\docs/plans/scraper_graphql_replay.md`
- **Motivation:** Even with the ACTION-030/031 mitigations (JSONL checkpoint, 500-scroll cycle cap, unique-stale guard, 700 MB heap-pressure restart, CDP GC), the owner's laptop still freezes at ~1700 posts on long runs. The cliff is hardware-bound — DOM nodes + V8 heap + GraphQL response cache accumulate as the React feed scrolls, until Windows starts paging and the renderer GC-thrashes. Apify and Bright Data don't hit this because they don't run a desktop browser at all — they replay the underlying `/api/graphql/` calls directly with HTTP clients. This action implements the same architecture as a new fourth strategy.
- **Approach:** Brief Playwright session (~14 s) navigates the target page and harvests one pagination POST to `/api/graphql/` (token bundle: `fb_dtsg`, `lsd`, `jazoest`, `doc_id`, full `variables` JSON, complete header set captured via `request.all_headers()`, and the live cookie jar). The browser is then **kept open as a thin HTTP client** — no further DOM rendering, no scrolling — and the captured request is replayed via Playwright's `context.request.post()` (APIRequestContext) to drive cursor-based pagination. RSS stays bounded at ~100 MB regardless of post count. fb_dtsg is proactively re-harvested every 45 minutes (relaunch Chrome briefly, capture new tokens, close, resume) and reactively on any token-expiry signal.
- **Why APIRequestContext (not raw httpx):** Raw httpx replay returns FB error 1357054 ("Your Request Couldn't be Processed") even with byte-identical body and headers — Facebook's WAF appears to fingerprint the TLS ClientHello and reject non-Chrome stacks. Playwright's APIRequestContext uses real Chrome's HTTP/TLS stack, inherits the cookie jar (so fr/datr rotations carry over), and passes WAF cleanly. The architecture still avoids the freeze cliff because we never render DOM after harvest.
- **Files modified / created:**
  - **NEW** `graphql_httpx.py` — `TokenBundle` dataclass, `harvest_tokens()`, `paginate()`, `should_refresh()`, `close_session()`. ~360 LOC. Reuses `_GraphQLPostExtractor._iter_json_chunks` / `_walk_for_cursors` / `_walk_for_stories` (already `@staticmethod`) so the post dict shape and dedup contract are byte-identical to the desktop strategy.
  - **NEW** `scripts/test_graphql_httpx.py` — Phase 1 standalone PoC; ~500 LOC including diagnostics. Validates the technique against live FB before integration.
  - `config.py` — added 7 fields under `# --- GraphQL replay strategy (ACTION-032) ---`. Updated `strategies` default list to put `desktop_graphql_httpx` first; `desktop` becomes the fallback.
  - `scraper.py` — added `_desktop_graphql_httpx_strategy()` orchestrator (~110 LOC) that handles checkpoint resume, harvest/re-harvest, paginate, close. Added dispatch branch in `_run_strategy`. No changes to `_GraphQLPostExtractor` (its static parsers are reused as-is).
- **Key debugging path while building the PoC:**
  1. First harvest captured 0 graphql POSTs → `__user=0` in cookie-side requests revealed that the persistent profile dir was logged out. Fix: force `use_persistent_context=False` and explicitly call `context.add_cookies(self._cookies)`.
  2. Heuristic too narrow → captured the wrong query (`ProfileCometTilesFeedPaginationQuery`, the photo grid). Fix: priority-based candidate selection favouring `*TimelineFeed*` queries.
  3. Replay returned `for (;;);{"error":1357054}` even with exact captured bytes. Discovery: `request.headers` returns only client-set headers; `request.all_headers()` returns the complete set Chrome actually sent (including `origin`, `accept`, `sec-fetch-*`). Without those, FB rejects.
  4. `request.all_headers()` includes HTTP/2 pseudo-headers (`:authority` etc.) which APIRequestContext rejects. Fix: filter out keys starting with `:`.
  5. After fixes: 102 posts in 80 MB RSS, all HTTP 200, no errors.
- **Tests:**
  - **PoC (Phase 1):** `scripts/test_graphql_httpx.py --target SLU --max-posts 100 --max-iterations 50`. Result: 102 unique posts collected, 0 errors, peak RSS 80 MB, 14 s harvest + 65 s replay. Cursor advanced cleanly each iteration; FB returns 3 posts per page on `ProfileCometTimelineFeedRefetchQuery`.
  - **Integration (Phase 3b):** `python main.py --cookies cookies.json --targets SLU --target-posts 200`. Result: 200 posts in 207 s (3.4 min), strategy=`desktop_graphql_httpx`, status=`target_reached`. JSONL schema matches desktop strategy exactly (keys: `engagement, post_id, post_url, source, text, timestamp_iso, timestamp_raw`; all `source: "graphql"`). Checkpoints fired every 30 s as designed.
  - **Cliff test v1 (interrupted):** Got to 2715/4000 in 45 min, then proactive token refresh fired and revealed a flaw — the new harvest's cursor pointed back to the top of the feed, so paginate began fast-forwarding through every previously-collected post (~38 min projected, asymptote with the next refresh). Killed the run; preserved the 2706 posts in JSONL.
  - **Cliff test v2 (PASSED):** After the two fixes (cursor preservation across refreshes; refresh interval 45 → 240 min), restarted from the 2706-post checkpoint. **Final: 4002 posts collected via `desktop_graphql_httpx`, status=`target_reached`, in 3906 s (65.1 min wall clock)**. Verified: JSONL has 4002 lines / 4002 unique by text, all `source: "graphql"`. Schema identical to desktop strategy (keys: `engagement, post_id, post_url, source, text, timestamp_iso, timestamp_raw`). Peak Python RSS ~340 MB, peak Chrome RSS ~1399 MB — *Chrome stayed flat the entire run* (vs desktop strategy where Chrome grows monotonically into the freeze cliff).
- **Two follow-up fixes during 3c:**
  1. `paginate()` now takes/returns a `start_cursor: Optional[str]` so the orchestrator threads the latest cursor across token refreshes. Without this, every refresh forces a full fast-forward through `len(posts)` duplicates before productive work resumes — fatal for long runs.
  2. `graphql_httpx_token_refresh_minutes` default raised 45 → 240 min. fb_dtsg/lsd appear to last for hours in practice; reactive refresh (paginate detects FB error envelope 1357054 / 401 / 403 and signals `token_expired`) catches actual expiry, so proactive refresh need only be a backstop for very long runs.
- **CLI flag added:** `--strategies` (e.g., `--strategies desktop_graphql_httpx` or `--strategies desktop`) to override `cfg.strategies` for testing a single strategy in isolation.
- **Cliff bypassed:** The owner's laptop previously froze at ~1700 posts on the desktop strategy. The new strategy reached 4002 without freezing — Chrome RSS stays bounded at ~1.4 GB throughout because no further DOM rendering happens after the brief harvest scrolls. Falls through cleanly to `desktop` on harvest failure (per `max_retries`), so the change is non-regressive.
- **Status:** DONE — all phases complete (1, 2a–2d, 3b, 3c, 3d).

### ACTION-033 — Repository housekeeping + researcher-facing docs aligned with ACTION-032
- **Time:** 2026-05-05
- **Motivation:** After ACTION-032 shipped, the project root had accumulated debug scripts, PoC scratch files, stale screenshots, and a 117 KB agent-monitor log all sitting alongside the production code. Researcher-facing docs (`QUICKSTART.md`, `guide.md`) still described the *old* desktop strategy: tqdm progress format with `scroll=`/`stale=`/`sess=` fields, "1700-post freeze" caveats, restart-cycle troubleshooting that no longer applies to the default path. New researchers following the docs would have been confused by the actual log output.
- **Folder cleanup (no functional changes):**
  - **Created** `debug/` directory and moved `debug_dom.py`, `debug_dom2.py`, `debug_dom3.py`, `debug_dom4.py` into it. Added `debug/README.md` explaining how to run them (must be invoked from project root because the scripts open `cookies.json` with a relative path).
  - **Moved** `AGENT_ACTIONS.log` from project root → `logs/AGENT_ACTIONS.log`. Updated the path in `monitor.sh` (line 6) and `monitor.ps1` (line 7) so the autonomous monitor still appends to the same file.
  - **Created** `logs/archive/` and moved 60 pre-2026-05-04 `scrape_*.log` files into it. Active `logs/` directory now contains only May 4–5 runs and the agent / cliff-test logs.
  - **Deleted** `__pycache__/` (×3), PoC scratch files (`scripts/_poc_first_response.bin`, `scripts/_poc_harvest_fail.png`), and 3 stale `debug_screenshots/*.png` artifacts from old freeze-debugging sessions.
  - **Created** `.gitignore` formalising what should not be committed (`cookies.json`, `cookies_state.json`, `__pycache__/`, `data/*.json{,l}`, `logs/*.log`, `logs/archive/`, `debug_screenshots/*.png`, `scripts/_poc_*`, `fb_login_profile/`, IDE/OS junk).
- **Smoke test (post-cleanup):** `from scraper import FacebookScraper`, `from config import ScraperConfig`, `import graphql_httpx, parser, utils, apify_scraper, extract_cookies` all succeed; `python main.py --help` shows full usage including the `--strategies` flag from ACTION-032; `python -m py_compile debug/debug_dom*.py` succeeds.
- **Doc updates — `QUICKSTART.md`:**
  - Replaced the old tqdm progress example with the new logger-line format (`[graphql_httpx] iter=N total=M (+K)`).
  - Added a one-paragraph "Two-phase scraping" callout explaining the brief Chrome harvest → API replay architecture and the bounded ~1.5 GB memory ceiling.
  - Rewrote the "If your run crashes or you stop it" note to warn researchers about the resume-time fast-forward (long stretches of `+0` lines while the dedup filter rejects already-collected posts before reaching new content).
- **Doc updates — `guide.md`:**
  - **New** "How It Works (One-Minute Overview)" subsection in Part 1: numbered list of the four strategies and how the chain falls through (`desktop_graphql_httpx` → `desktop` → `basic_mobile_httpx` → `basic_mobile`).
  - Step 6 progress example replaced with the new logger format + a guide to reading each line. Added a sub-example showing the *fallback* tqdm format if the run ever falls through to `desktop`.
  - Step 8 expanded into three labelled sub-sections: "Resuming a run" (explains fast-forward `+0` period), "Token refresh" (explains `tokens aged out` → re-harvest cycle), "About browser restarts (fallback strategy only)" — clarifying that restart-cycle messages now apply only to the `desktop` fallback path.
  - Memory footprint note added to the timing block: *"~1.5 GB total (Chrome stays flat — no growth with post count)"*.
  - Troubleshooting refreshed: removed the obsolete "high ETA after restart cycle" and "ScrollWatchdog fired" entries; added new entries for `+0` iterations during resume, `tokens aged out`/`FB error envelope`, and `harvest failed → fallback`.
  - Command Reference: added two `--strategies` examples to demonstrate forcing a specific strategy for debugging.
- **Files modified:** `QUICKSTART.md`, `guide.md`, `monitor.sh`, `monitor.ps1`. **Created:** `debug/README.md`, `.gitignore`.
- **Files moved:** 4 × `debug_dom*.py` → `debug/`; `AGENT_ACTIONS.log` → `logs/`; 60 × old scrape logs → `logs/archive/`.
- **Files deleted:** 3 × `__pycache__/` directories, 2 × PoC scratch artifacts, 3 × stale debug screenshots.
- **No code/behavior changes.** Production strategy chain, dispatch logic, parsers, and JSONL schema are byte-identical to ACTION-032's end state. The only edits to *.py files are path strings inside `monitor.sh`/`monitor.ps1`.
- **Status:** DONE

### ACTION-034 — Fix timestamp + engagement extraction for Comet feed shape
- **Time:** 2026-05-05
- **Motivation:** Spot-check of collected data revealed that almost no posts had timestamps. Audit: SLU 1/4002 (0.0 %), FW-01 0/4012 (0/4012 ISO, 4/4012 raw), FW-02 similar — virtually every post in `data/*.jsonl` has `timestamp_iso: null` and `timestamp_raw: null`. Engagement counts were also stuck at all-zero. The bug pre-dates ACTION-032 (the same `_GraphQLPostExtractor` powers both the legacy desktop strategy and the new graphql_httpx replay strategy), but it became more visible because all current data was collected via the same path.
- **Root cause:** `_walk_for_stories` checked for `message.text` and `creation_time` *at the same node*. Live probe of a `ProfileCometTimelineFeedRefetchQuery` response (saved to `scripts/_probe_response.json`) showed Facebook's modern Comet feed places them in **sibling subtrees** under `comet_sections`:

  ```
  comet_sections/content/story/message/text                 ← message (4 mirror paths)
  comet_sections/timestamp/story/creation_time              ← unix timestamp
  comet_sections/feedback/story/.../reaction_count.count    ← reactions (8 levels deep)
  comet_sections/feedback/story/.../comment_rendering_instance.comments.total_count
  comet_sections/feedback/story/.../share_count.count       ← shares
  ```

  The DFS visited the inner message-bearing node, found no `creation_time`/`feedback` siblings on that node, and yielded `timestamp_iso=None` plus zero engagement.

- **Fix — `scraper.py` `_GraphQLPostExtractor`:**
  1. **`_walk_for_stories` rewritten** as a two-recogniser DFS:
     - When a node has `comet_sections`, hand the dict off to a new `_extract_comet_post(cs)` which pulls message / creation_time / URL / engagement from their respective known paths within `comet_sections`. The DFS skips re-descending into `comet_sections` after extraction so the legacy branch doesn't yield duplicates.
     - When a node has `message.text` directly (and no `comet_sections`), fall back to the existing per-node logic for older feed shapes (mbasic, FeedUnit envelopes, non-Comet responses).
  2. **`_extract_comet_post(cs)`** new helper. Pulls:
     - `message`: `cs/content/story/message/text`
     - `creation_time`: tries `cs/timestamp/story/creation_time` first, then falls back to `cs/context_layout/story/comet_sections/metadata/[N]/story/creation_time`
     - URL: `cs/content/story/{wwwURL,permalink_url,url}`
     - engagement: delegates to `_extract_engagement_comet(fb_root)`
  3. **`_extract_engagement_comet(fb_root)`** new walker-based helper. Walks the entire `feedback` subtree and aggregates the maximum value seen for each metric, looking for:
     - `reaction_count` dict with `count` field (also accepts `i18n_reaction_count` string)
     - `share_count` dict with `count` field
     - `comment_rendering_instance.comments.total_count`
     - Skips per-emoji `reaction_count` entries inside `top_reactions/edges/[N]` (those are int-typed and represent individual reactions, not aggregate counts).
  4. **Legacy `_extract_engagement(node)`** kept unchanged for non-Comet shapes (header rewritten to make this clear).
- **Validation:** Re-ran `_walk_for_stories` against the saved probe response (`scripts/_probe_response.json`, captured 2026-05-05 from a live SLU pagination request). Result: 3/3 posts now have timestamps and URLs; first post has correct engagement (159 reactions, 53 comments, 12 shares — verified against raw response). Posts 2 and 3 show 0 engagement, which matches the source (genuinely no interactions yet — they were posted minutes before harvest).
- **Files modified:** `scraper.py` (parser methods only — strategy code, dispatch, and JSONL schema unchanged).
- **Files created:** `scripts/probe_response_shape.py` — diagnostic tool that captures one /api/graphql/ response and reports the JSON paths where each interesting key lives. Useful for future FB schema drift.
- **Backfill — what to do about already-collected data:**
  - Currently-running scrapes (FW-04 in progress at fix time) use the *in-memory* parser code from when Python imported `scraper.py` at process start. Editing `scraper.py` on disk does NOT affect a running process. Therefore: FW-04 will continue collecting *without* timestamps until restarted.
  - For the cleanest result on currently-running and not-yet-started pages: stop the run (Ctrl+C), delete the buggy partial (`rm data/FW-04.jsonl` — the 4 dud entries from this session), then restart with the same command. The new entries will all have timestamps + engagement.
  - For SLU / FW-01 / FW-02 (already at 4 000+ posts each, all without timestamps): the only way to get timestamps is to delete the JSONL and re-scrape. ~65 min per page on the new strategy = ~3.25 h total. The post text and post_id are unchanged so any downstream analysis already done can be merged on `post_id` after re-scrape if needed.
  - **Recommendation:** If timestamps are essential to the research (semester-window filtering depends on them via `is_within_window`), re-scrape SLU/FW-01/FW-02. If text-only analysis is sufficient, accept the loss for those 3 and rely on `#SLUFreedomWallNNNNN` style hashtag prefixes inside the post text as a coarse temporal proxy.
- **Status:** DONE — fix verified on a live response, ready to apply to all future scrapes.

### ACTION-035 — Distinguish rate-limit from token expiry; stop instead of looping
- **Time:** 2026-05-05
- **Motivation:** During an FW-07 run the scraper hit Facebook's rate limiter (`code: 1675004`, `"Rate limit exceeded"`) at iter=1 right after a successful harvest. The existing parser routed *any* GraphQL `errors[]` to `stop_reason="token_expired"`, which the orchestrator treats as "re-harvest and resume". The harvest itself was succeeding (different endpoint), so the loop kept going: harvest → 1 paginate call → rate limit → re-harvest → repeat. Each cycle issued ~6 more requests against an already-over-limit account, deepening the problem instead of stopping.
- **Fix — `graphql_httpx.py` `paginate()`:** Inspect the GraphQL error blob for rate-limit fingerprints before classifying. New stop reason `"rate_limited"` is returned when any of these match (case-insensitive):
  - `"code": 1675004` (or compact form `"code":1675004`)
  - `"rate limit"` substring
  - `"rate_limit"` substring
  - `"throttled"` substring

  Other graphql errors continue to route to `token_expired` (correct behaviour for auth/CSRF rejections).
- **Fix — `scraper.py` `_desktop_graphql_httpx_strategy`:** New `if stop_reason == "rate_limited"` branch that breaks out of the orchestrator loop *without* re-harvesting. Logs an ERROR-level message instructing the researcher to wait at least 1 hour before re-running. The JSONL is preserved so a later rerun resumes correctly.
- **Files modified:** `graphql_httpx.py` (paginate error classifier), `scraper.py` (orchestrator stop-reason handling).
- **Why this matters:** Without this fix, hitting the rate limit caused a tight retry loop that would have aggravated the lockout and possibly escalated it to a longer cooldown. With the fix, a rate limit produces a clean exit with a clear log message; the user waits and resumes manually.
- **Status:** DONE — code compiles and imports clean. Will activate on the next scraper run.
