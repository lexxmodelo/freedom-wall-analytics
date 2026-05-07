# Freedom Wall Scraper — Apify-Style Reliability Improvements

## Context

The current scraper uses Playwright for everything (both `desktop` and `basic_mobile` strategies). It freezes inconsistently across machines: the owner reaches ~1600–1700 posts; some users freeze at 500+ even with 16 GB RAM. mbasic via Playwright also freezes sometimes with no clear cause.

### Why the inconsistency happens (already diagnosed)

The freeze cliff is **not** purely a heap problem — `--max_old_space_size=2048` and the 700 MB heap-pressure restart at [scraper.py:1208–1222](scraper_project/scraper.py:1208) prove that. The accumulating pressures, in order of likely impact:

1. **CDP IPC stall.** Chrome DevTools Protocol message passing between Python ↔ Chromium becomes unresponsive once eval payloads grow. Hardware/OS-dependent (per-core throughput, ProactorEventLoop subprocess buffering). This is why "16 GB RAM" doesn't save users — RAM isn't the bottleneck, IPC throughput is.
2. **DOM accumulation as O(N²).** [`_cleanup_dom`](scraper_project/scraper.py:1703) sets `innerHTML=''` on parsed posts but leaves placeholder `<div>`s in place. After 200 scrolls, `querySelectorAll('div')` walks ~1000+ elements per scroll. The 2000-div guard at [scraper.py:1653](scraper_project/scraper.py:1653) papers over this.
3. **V8 heap fragmentation.** React keeps object graphs entangled; CDP `HeapProfiler.collectGarbage()` can't reclaim fragmented old-space.
4. **Bundled Chromium vs system Chrome.** [config.py:80](scraper_project/config.py:80) sets `channel="chrome"`, so behavior is gated on the user's installed Chrome version.
5. **Network response buffering.** GraphQL extractor accumulates posts faster than DOM cleanup runs.

The owner's machine probably has higher single-core CDP throughput and a Chrome version that handles backpressure better — that's why they get to ~1700 while others freeze at 220–500.

### Goal

Three changes, shipped in order, each independently verifiable:

1. **Append-only JSONL checkpointing** — crash safety, independent of everything else.
2. **Aggressive context cycling** (500 → 100 scrolls) — restart well before the freeze cliff.
3. **mbasic-primary via httpx** — eliminate Playwright entirely for the primary scrape path; mbasic.facebook.com is server-rendered HTML, no JS needed.

Static proxy support is **out of scope** for this change.

---

## Change 1 — Append-only JSONL checkpointing

### Why first

Independent of the other two. Zero risk of breaking scrape logic. Crash-safety win that pays off immediately because Change 2 will increase restart frequency.

### Files / lines

- [scraper.py:1425–1431](scraper_project/scraper.py:1425) — replace `_checkpoint_save` body.
- [scraper.py:1232–1255](scraper_project/scraper.py:1232) — caller stays unchanged externally.
- [scraper.py:925–946](scraper_project/scraper.py:925) — resume block in `_desktop_run`. Replace JSON-load with JSONL line-iterate.
- [scraper.py:829](scraper_project/scraper.py:829) area (`scrape_target` end) — convert JSONL → final `{metadata, posts}` JSON deliverable.

### Shape

```
# scraper.py
self._jsonl_written_ids: dict[str, set[str]] = {}  # init in __init__

def _checkpoint_save(self, posts, code):
    path = os.path.join(self.cfg.output_dir, f"{code}.jsonl")
    written = self._jsonl_written_ids.setdefault(code, set())
    with open(path, "a", encoding="utf-8") as f:
        for p in posts:
            pid = p["post_id"]
            if pid in written:
                continue
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
            written.add(pid)

def _checkpoint_load(self, code) -> list[dict]:
    # Tolerant line-by-line read; skip malformed last line (mid-write crash recovery).
    # Also: if {code}.jsonl missing but {code}_checkpoint.json exists, migrate once.
    ...

def _finalize_jsonl(self, code, metadata) -> dict:
    posts = self._checkpoint_load(code)
    return {"metadata": metadata, "posts": posts}
```

### Risks

- **Mid-write corruption.** Tolerant load skips a malformed last line; the dropped post is recollected on resume via `post_id` dedupe.
- **Orphaned `{code}_checkpoint.json` files.** Add one-time migration in `_checkpoint_load`.
- **Final deliverable schema unchanged.** main.py still receives the same `{metadata, posts}` shape.

---

## Change 2 — Aggressive context cycling (500 → 100)

### Why second

One-line config change. Most likely fix for users freezing at 220–500 — restarts before the cliff regardless of which underlying pressure (CDP/DOM/heap) dominates on their machine.

### Files / lines

- [config.py:61](scraper_project/config.py:61) — `max_scrolls_per_session: int = 500` → `100`.
- [config.py:62](scraper_project/config.py:62) — keep `session_restart_threshold` aligned at 100.
- [scraper.py:431](scraper_project/scraper.py:431) — `fast_forward_via_extractor` `target_fresh_posts` default `30` → `15`. Less strict boundary cuts fast-forward overhead roughly in half. Safe because the dedupe set rejects overlap downstream.

No code change to `_SessionRestarter.cycle()` at [scraper.py:355–425](scraper_project/scraper.py:355) — it already handles save/teardown/relaunch/fast-forward.

### Risks

- **Fast-forward overhead.** If the average restart costs 50 scrolls of duplicates, 100-scroll sessions yield only ~50 net useful scrolls each. Lowering `target_fresh_posts` to 15 mitigates this. Worst case: revert to 150 if total throughput regresses below current baseline on the owner's machine.
- **Heap-pressure backstop at 700 MB still active** ([scraper.py:1214](scraper_project/scraper.py:1214)) — defense in depth.

---

## Change 3 — mbasic-primary with httpx

### Why third

Biggest reliability win — eliminates Playwright entirely for the primary path on cooperating targets. Largest surface area, so ship after 1+2 are baked. The user confirmed mbasic *does* scrape today via Playwright but freezes sometimes; httpx removes the freeze vector entirely (no CDP, no DOM, no V8) for this path.

### Files / lines

- [requirements.txt](scraper_project/requirements.txt) — add `httpx>=0.27.0`.
- [config.py:118–121](scraper_project/config.py:118) — strategy order becomes `["basic_mobile_httpx", "desktop", "basic_mobile"]`. Old Playwright-mbasic kept as third tier for the rare case httpx is blocked but headed Chrome isn't.
- [config.py](scraper_project/config.py) — add:
  ```
  mbasic_request_delay_min: float = 3.0
  mbasic_request_delay_max: float = 6.0
  ```
- [scraper.py:859–865](scraper_project/scraper.py:859) (`_run_strategy`) — dispatch `basic_mobile_httpx` to new method.
- [scraper.py](scraper_project/scraper.py) — add `_basic_mobile_strategy_httpx`, sibling of [`_basic_mobile_strategy`](scraper_project/scraper.py:1435). Reuses existing `BasicMobileParser` at [parser.py:230+](scraper_project/parser.py) verbatim.

### Shape

```
def _basic_mobile_strategy_httpx(self, url, code) -> list[dict]:
    # 1. Same URL transformation as _basic_mobile_strategy:1439-1445
    #    (rewrite www.facebook.com -> mbasic.facebook.com, normalize path).
    # 2. Build cookie jar from self._cookies (Playwright format -> httpx.Cookies).
    # 3. httpx.Client(
    #        cookies=jar,
    #        headers={UA: Pixel-7 Android (same as scraper.py:1459-1463),
    #                 Accept-Language: en-US,en;q=0.9,
    #                 Accept-Encoding: gzip},
    #        follow_redirects=True,
    #        timeout=30,
    #    )
    # 4. Loop:
    #    resp = client.get(current_url)
    #    Block detection:
    #      - "you must log in" in resp.text
    #      - resp.url.path startswith "/checkpoint/"
    #      - resp.url.host != "mbasic.facebook.com" (FB redirected to m.facebook.com)
    #      - HTTP >=400
    #    -> raise BlockedByMbasic; caller falls through to desktop strategy.
    #    Otherwise: posts, next_url = BasicMobileParser.parse_page(resp.text)
    #    Dedupe by post_id, append, _checkpoint_save every 30s.
    # 5. Stop conditions same as _basic_mobile_strategy:1513-1519
    #    (target_posts reached / next_url None / new_count == 0).
    # 6. Sleep random.uniform(mbasic_request_delay_min, max) between requests.

def _cookies_to_httpx(self) -> httpx.Cookies:
    jar = httpx.Cookies()
    for c in self._cookies:
        if "facebook.com" not in c.get("domain", ""):
            continue
        jar.set(c["name"], c["value"],
                domain=c["domain"].lstrip("."),
                path=c.get("path", "/"))
    return jar
```

### Why this will work

- mbasic.facebook.com is **server-rendered HTML** — Playwright was doing nothing useful there. [`_basic_mobile_strategy`](scraper_project/scraper.py:1435) calls `page.goto()` then `page.content()`; the latter returns the same body `httpx.get(...).text` returns. No JS, no clicks, no scroll.
- `BasicMobileParser` is pure BeautifulSoup — already parses HTTP-fetchable HTML. Reusable verbatim.
- Existing `cookies.json` is in Playwright cookie format; mechanical conversion to `httpx.Cookies()`. Strip leading dots from `.facebook.com` for httpx subdomain matching.
- Pagination via `<a>` next-link is already extracted by parser at [parser.py:486–495](scraper_project/parser.py:486).

### Risks

- **Token expiry.** `c_user`, `xs`, `fr` cookies rotate. Same recovery as today (re-extract cookies). No new failure mode.
- **mbasic redirect to m.facebook.com.** Detected via `resp.url.host` check; treated as block, falls back to desktop. Existing UA from [scraper.py:1459–1463](scraper_project/scraper.py:1459) avoids this in practice.
- **httpx blocked AND desktop blocked.** Becomes the new ceiling for some users — but that's the same ceiling they have today.
- **Brotli skipped** (no `httpx[brotli]` extra) to avoid Windows dependency drift. gzip is sufficient.

---

## Critical files to modify

- [scraper_project/scraper.py](scraper_project/scraper.py) — Changes 1, 2, 3
- [scraper_project/config.py](scraper_project/config.py) — Changes 2, 3
- [scraper_project/requirements.txt](scraper_project/requirements.txt) — Change 3 (add httpx)
- [scraper_project/parser.py](scraper_project/parser.py) — **read only**, reused verbatim
- [scraper_project/main.py](scraper_project/main.py) — likely no change; final-deliverable schema is preserved by `_finalize_jsonl`

## Reused existing code

- [`BasicMobileParser`](scraper_project/parser.py) (parser.py:230+) — reused without modification by Change 3.
- [`_SessionRestarter.cycle()`](scraper_project/scraper.py:355) — reused without modification by Change 2.
- [`_GraphQLPostExtractor`](scraper_project/scraper.py:39) — left intact; still useful for the desktop fallback path.
- Existing per-strategy dispatch at [scraper.py:801–865](scraper_project/scraper.py:801) — extended, not rewritten.

---

## Ship order (do not bundle)

1. **Change 1** (JSONL) — verify on one normal `desktop` run; confirm `{code}.jsonl` writes incrementally and `{code}.json` final deliverable matches today's schema.
2. **Change 2** (cycle 100) — verify on the affected user's machine that a run gets past 500 scrolls without freezing. Compare total throughput vs baseline on the owner's machine.
3. **Change 3** (mbasic httpx) — verify with one FW page using saved cookies. Confirm posts are returned without invoking Playwright at all.

Each change ships in its own commit so a regression can be isolated.

---

## Verification

### Change 1
- Run on one FW target with a small `--target-posts 50`. Watch `data/{code}.jsonl` grow line-by-line (`tail -f` equivalent).
- Kill the process mid-run. Re-run. Confirm resume reads JSONL, dedupes, continues.
- At end of run, confirm `data/{code}.json` exists with `{metadata, posts}` schema unchanged from current main.py expectations.

### Change 2
- Run on the owner's machine: confirm total post count is within ~10% of current baseline (~1600–1700). If it drops more, fast-forward overhead is higher than expected and `target_fresh_posts=15` may need to drop further or restart cap may need to raise to 150.
- Run on an affected user's machine (one that froze at 220–500): confirm the run completes a full target without freezing.

### Change 3
- Smoke test: open a Python shell, instantiate the cookie jar from `cookies.json`, do `httpx.get("https://mbasic.facebook.com/SaintLouisUniversityFreedomWall")` (or equivalent FW page). Confirm response is mbasic HTML, not a login wall or redirect to m.facebook.com.
- Pass response body to `BasicMobileParser.parse_page` directly. Confirm it returns posts.
- Run full strategy on one FW target. Confirm posts collected without launching Chromium at all (check Process Explorer / Task Manager — no `chrome.exe` from Playwright).
- Force a block path: temporarily corrupt cookies, confirm `BlockedByMbasic` raises and dispatcher falls through to `desktop`.

---

## Out of scope (explicitly rejected)

- **Static proxy support.** Trivial code (`proxy={"server": ...}` in launch + httpx). Excluded per user choice; can be added later in 10 lines.
- **Async Playwright migration.** Python 3.14 / Windows incompatibility (action_log ACTION-007).
- **CAPTCHA bypass / proxy auto-rotation.** Out of scope.
- **CDP-latency adaptive restart.** Heap-pressure backstop at 700 MB is the existing analog; 100-scroll cap is the new primary lever. Adaptive logic is cumulative complexity.
- **Rewriting `_cleanup_dom` to actually remove placeholder DIVs.** Tempting (it's the O(N²) cause) but a behavioral change on the proven desktop path. Don't break what works for the owner; sidestep it via cycling instead.
