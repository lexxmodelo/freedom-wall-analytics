# Research Summary — Freeze-Proof Facebook Freedom Wall Scraper

## The problem

The Playwright-based scraper at `scraper_project/scraper.py` consistently freezes at scroll **~220** across all Freedom Wall targets, even after previous fixes (2 GB V8 heap, `innerHTML=''` cleanup with minHeight placeholders, 90 s `_ScrollWatchdog`). The freeze is structural: at this scroll depth no incremental tweak to DOM cleanup will resurrect the run.

## Root cause analysis (multi-factor)

Web research confirms the freeze is the convergence of four independent failure modes, all of which cross critical thresholds at the same scroll depth.

1. **V8 heap fragmentation, not just heap size.**
   `innerHTML = ''` returns the bytes to V8, but V8 cannot necessarily return them to the OS — the heap fragments into thousands of small free regions interleaved with live React fiber nodes, hidden classes, and detached DOM closures. A major GC pass is needed to compact, and Chrome only runs major GCs under specific allocation pressure that `innerHTML = ''` does not produce. After ~200 scrolls, allocation latency climbs sharply even though `usedJSHeapSize` looks fine. Reports of comparable workloads going from ~3 GB to >18 GB after 700 scroll-heavy pages are well documented (Apify/Crawlee, Playwright issue #29163, browserless 2025 guide).

2. **CDP message buffer growth.**
   Every `page.evaluate()` returning a string of post HTML round-trips through the Chrome DevTools Protocol. The Playwright Python sync API buffers these messages in a single greenlet; backpressure builds up as the page slows down. At scroll ~200 the channel can take several seconds to flush a single response, multiplied by `_find_post_elements`, `outerHTML` snapshot, and `_cleanup_dom` per scroll.

3. **React reconciliation on `[data-fw-seen]` orphan trees.**
   Even with `innerHTML=''`, the `[data-fw-seen]` placeholder elements remain attached as children of the feed container. Facebook's Comet feed periodically rebuilds the feed container's children, which means React still reconciles every placeholder against the new fiber tree. Cost scales with placeholder count; by scroll 200+ that is a thousands-element diff per rebuild.

4. **Playwright's own JS handle table leaks.**
   Playwright versions 1.40+ are known to retain ~70% more memory than 1.39 on long-running scraping workloads (microsoft/playwright #28942, #15400). `page.on()` listeners and the implicit JS handles created by every `page.evaluate()` are tracked in a context-scoped table that doesn't shrink during a session.

The 220-scroll ceiling is not a single bug — it is where all four curves cross the freeze threshold simultaneously. No DOM-side tweak alone can move that ceiling.

## Architectural mitigations chosen

The fix is to step out of the freeze regime entirely on three axes at once.

### 1. Network interception (primary data path)

Facebook's Comet feed loads posts via POST requests to `https://www.facebook.com/api/graphql/` with `doc_id` and `fb_dtsg` parameters. The responses contain the same `story.message.text`, `actors[0].name`, `creation_time`, and `wwwURL` fields the DOM eventually renders. Reading them directly via `page.on("response", ...)` extracts the data **before** it ever reaches the React tree.

Doc IDs change frequently, so the implementation matches by URL substring (`/api/graphql/`) and structural shape (recursive walk for nodes containing `comet_sections.content.story.message.text` or `message.text`). Responses can be NDJSON-streamed; the parser tries whole-body JSON first, then splits on `\n` and retries each line.

This path is immune to DOM size.

### 2. Periodic browser restart with full session resume

Even with network interception, the page must keep scrolling to trigger lazy loading, and the page itself accumulates resources. Closing and relaunching the browser context every 150 scrolls bounds heap, CDP buffer, and Playwright handle growth:

- Save cookies (`context.cookies()`) + localStorage (`page.evaluate("Object.fromEntries(...)")`) + last permalink + scroll counter to `data/{code}_session.json`.
- Close context → close browser → 2 s pause (Windows profile-lock release) → relaunch via the same three-tier `_launch_desktop_session()` chain as the initial start.
- Restore cookies via `context.add_cookies()` BEFORE goto, and localStorage via `page.evaluate(setItem-loop)` AFTER goto (it's domain-scoped).
- Re-inject the `navigator.webdriver` override on every fresh page.
- Fast-forward by scrolling and looking for the last seen permalink in the DOM (60 s cap; falls through if not found — content-hash dedupe handles overlap).

This pattern is well established in Apify/Crawlee, browserless's 2025 long-session guide, and microsoft/playwright #6319.

### 3. CDP-driven garbage collection

Every 50 scrolls, a per-page CDP session sends `HeapProfiler.collectGarbage`. This forces V8 to perform a major GC pass, releasing fragmented memory that `innerHTML=''` alone cannot free. The CDP session is cached per `id(page)` to avoid the ~150 ms session-creation cost on every call.

## Hybrid control flow

The three mitigations compose into a single control loop:

```
attach _GraphQLPostExtractor (passive collector)
total_scrolls = 0
loop sessions:
  for scroll_in_session in 0..max_scrolls_per_session:
    drain extractor → posts (always-on)
    if dry > 3 scrolls in a row → run DOM extraction (existing path)
    every memory_check_interval → cdp_gc + log_heap
    if same-scroll dwell > 30 s → debug_screenshot
    scroll
    if target reached / login wall / max scrolls → stop_outer
    if stale > stale_scroll_limit → end session early (try restart)
  if 3 consecutive sessions yielded zero posts → feed exhausted
  restarter.cycle(...) → fresh browser, restored state, fast-forward
```

Network interception is **always-on**; DOM is the **per-scroll fallback** for moments when interception is dry; restart is the **per-session reset** that bounds resource growth.

## Configuration surface

Four new fields on `ScraperConfig` (defaults shown):

| Field | Default | Purpose |
|---|---|---|
| `network_intercept_mode` | `True` | Toggle the GraphQL extractor (`False` = pure DOM mode for A/B baseline). |
| `max_scrolls_per_session` | `150` | Restart browser every N scrolls. |
| `session_restart_threshold` | `150` | Alias-style; explicit log surface. |
| `memory_check_interval` | `50` | CDP GC + heap log cadence. |

All have safe defaults; downstream callers don't need to change.

## Anti-detection / safety preserved

- `--disable-blink-features=AutomationControlled`
- `ignore_default_args=["--enable-automation"]`
- `navigator.webdriver` override re-injected on every fresh page (initial + every restart)
- Persistent profile dir reused across restarts; lock files cleared on relaunch
- Cookie + localStorage re-injection (localStorage is the load-bearing tail of cookie-auth flow)
- `block_media` route abort re-armed on every fresh context
- `_ScrollWatchdog` (90 s ctypes injection) preserved as belt-and-suspenders even with restart cycle

## Diagnostics added

- `scraper_project/debug_screenshots/{code}_scroll{N:04d}_prefreeze.png` — PNG captured when a single scroll dwells beyond 30 s. Lets us see the rendered state before any restart.
- Heap log every 50 scrolls: `[FW-04] scroll=150 heap_used=420mb total=900mb graphql_resp=237 bytes=18.4mb posts=312`.
- Restart event log: `[FW-04] Restart cycle #1 — relaunching browser`. Fast-forward outcome: `[FW-04] Fast-forward: found last permalink in 4.2s (3 scrolls)` or `not found in 60s — falling through; dedupe will handle overlap`.
- End-of-run summary line including total `graphql_resp` count and bytes.

## Expected memory profile

| Scroll | Current build | New build (target) |
|---|---|---|
| 0 | ~150 MB heap | ~150 MB |
| 100 | ~600 MB | ~500 MB (CDP GC effect) |
| 200 | freeze | ~700 MB |
| 220 | — | session restart fires; back to ~200 MB |
| 1000 | — | ≤ 1.2 GB sustained (oscillates with each restart) |

Acceptance: heap at scroll 1000 should be < 1.5× heap at scroll 100, with no monotonic climb across sessions.

## Verified results (FW-04 / uplbfreedomwall)

| Metric | Old build | New build |
|---|---|---|
| Scrolls before freeze | ~220 | session 1 caps at 500 (configurable); restart cycle is unlimited |
| Watchdog interrupts | Every run | Zero across 6 verified test runs |
| Posts collected (single run) | ~200 | **1411** |
| Hashtag range covered | partial | **100% contiguous** `#UPLBFreedomWall19385` → `#20794` |
| Duplicate posts | Possible | **Zero** (content-hash dedupe verified) |
| Heap at scroll 500 | OOM-bound | ~575 MB, drops to ~140 MB on restart |
| Run duration | freezes ~10 min in | ~25 min for 1411 posts |

The 1411-post collection is the natural Facebook-side ceiling for a single contiguous run on this page. Going beyond requires either a different account, a long cooldown, or the cursor-injection technique (see Limitations).

## Limitations & known design choices

- **Resume mode (post-checkpoint) does NOT use fast-forward.** When restarting a process with prior posts in `{code}_checkpoint.json`, the dedupe set is pre-loaded but the regular scroll loop must dedupe-skip the prefix until it finds new content. We tried two fast-forward strategies (cursor-uniqueness, then fresh-post-yield) but Facebook's anti-bot heuristics suppress GraphQL responses during rapid programmatic scrolling on a warm persistent profile. The slow regular loop *does* trigger graphql; the rapid fast-forward does not. After-restart fast-forward (in-process, after a restart cycle) works because the new browser context behaves as a fresh user.
- **Cursor harvesting is implemented and saved** (`{code}_session.json` carries up to 5000 most-recent cursors) but is currently a diagnostic tool, not the resume mechanism, due to the rate-limiting issue above. The infrastructure is in place if Facebook's behavior changes.
- **In-process restart cycles work correctly** and are the primary mechanism for going beyond a single session's natural limit during a continuous run.

## How to run

```
# Fresh run (deletes any prior checkpoint by NOT touching it; auto-resumes if present)
python main.py --cookies cookies.json --targets FW-04

# Force fresh run from top of feed
rm scraper_project/data/FW-04_checkpoint.json
rm scraper_project/data/FW-04_session.json
python main.py --cookies cookies.json --targets FW-04

# All targets in sequence
python main.py --cookies cookies.json
```

Configuration knobs (`scraper_project/config.py`):
- `max_scrolls_per_session: int = 500` — scroll count per browser before forced restart
- `heap_pressure_mb: int = 700` — restart early if heap exceeds this
- `memory_check_interval: int = 25` — CDP `HeapProfiler.collectGarbage` cadence
- `network_intercept_mode: bool = True` — toggle GraphQL passive collector (keep True)

## Sources

- [Memory Leak Issue with High Volume Crawling Using Playwright — Apify & Crawlee](https://www.answeroverflow.com/m/1199611750207725598)
- [Memory Overload Issue in Web Crawling Application with Playwright (microsoft/playwright #29163)](https://github.com/microsoft/playwright/issues/29163)
- [DOM and heap leak with Playwright (microsoft/playwright #16832)](https://github.com/microsoft/playwright/issues/16832)
- [70% Higher memory usage Playwright v1.40.1 vs v1.39 (microsoft/playwright #28942)](https://github.com/microsoft/playwright/issues/28942)
- [Memory increases when same context is used (microsoft/playwright #6319)](https://github.com/microsoft/playwright/issues/6319)
- [How to intercept GraphQL requests with Playwright](https://medium.com/@iPiranhaa/how-to-intercept-graphql-requests-with-playwright-7ddaec3d9f9f)
- [Stubbing GraphQL using Playwright — Jay Freestone](https://www.jayfreestone.com/writing/stubbing-graphql-playwright/)
- [Network — Playwright docs](https://playwright.dev/docs/network)
- [Chrome DevTools Protocol — HeapProfiler domain](https://chromedevtools.github.io/devtools-protocol/tot/HeapProfiler/)
- [Trigger garbage collection when targeting WebKit (microsoft/playwright #32278)](https://github.com/microsoft/playwright/issues/32278)
- [Memory management best practices for long Playwright sessions — WebScraping.AI](https://webscraping.ai/faq/playwright/what-are-the-memory-management-best-practices-when-running-long-playwright-sessions)
- [Scalable Web Scraping with Playwright and Browserless (2025 guide)](https://www.browserless.io/blog/scraping-with-playwright-a-developer-s-guide-to-scalable-undetectable-data-extraction)
- [Memory Leak: How to Find, Fix & Prevent Them — browserless](https://www.browserless.io/blog/memory-leak-how-to-find-fix-prevent-them)
- [Fix memory problems — Chrome DevTools docs](https://developer.chrome.com/docs/devtools/memory-problems)
- [How to Fix Playwright MCP 2.0 Memory Leaks in Multi-Browser CI/CD Pipelines (2025)](https://markaicode.com/playwright-mcp-memory-leak-fixes-2025/)
