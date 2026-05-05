"""
GraphQL replay strategy — ACTION-032.

Bypasses the V8/Chrome-RSS freeze cliff by harvesting one /api/graphql/
pagination request via a brief Playwright session, then replaying that
request through the same browser's APIRequestContext. The browser remains
open as a thin HTTP client (no further DOM rendering, no scrolling), so
RSS stays bounded at ~100 MB regardless of post count.

Why APIRequestContext (vs raw httpx):
  - Real Chrome TLS fingerprint passes Facebook's WAF. Raw httpx returns
    error 1357054 ("Your Request Couldn't be Processed") even with
    byte-identical body and headers.
  - Cookie jar auto-rotates (fr/datr/i_user refreshes) without our help.
  - request.all_headers() gave us the complete header set Chrome actually
    sent (including origin / sec-fetch-* / accept that aren't visible to
    page.on("request") via request.headers).

Public surface:
  TokenBundle           dataclass holding live browser session + replay info
  harvest_tokens()      brief scroll-driven capture of one pagination POST
  paginate()            replay loop; appends to posts list, persists JSONL
  should_refresh()      proactive token rotation predicate
  close_session()       tear down the kept-alive Playwright session

This module DOES NOT modify scraper state directly — the caller (the
desktop_graphql_httpx strategy method) owns posts/seen_hashes/checkpointing
and threads them into paginate() so resume from a JSONL checkpoint works
identically across strategies.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Optional

from utils import post_hash, random_sleep


# ---------------------------------------------------------------------------
# Pagination-request priority (higher = better replay target)
# ---------------------------------------------------------------------------
# ProfileCometTimelineFeed* returns the wall posts we want; Tiles returns
# the photo grid; CometFeed* covers groups/pages variants.
_FRIENDLY_PRIORITY: list[tuple[str, int]] = [
    ("profilecomettimelinefeed", 100),
    ("comettimelinefeed",         90),
    ("timelinefeed",              80),
    ("groupsfeed",                75),
    ("pagefeed",                  70),
    ("timeline",                  60),
    ("cometfeed",                 50),
    ("feedpagination",            40),
    ("pagination",                10),
    ("tiles",                      1),
]

# Denylist for replay headers. Hop-by-hop, content-length (httpx/PW
# computes), and accept-encoding (let the client negotiate). Cookie is
# managed by the cookie jar.
_REPLAY_HEADER_DENYLIST: set[str] = {
    "host",
    "content-length",
    "cookie",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "accept-encoding",
}


# ---------------------------------------------------------------------------
# TokenBundle — opaque handle returned by harvest_tokens
# ---------------------------------------------------------------------------

@dataclass
class TokenBundle:
    """All state required to drive the pagination loop.

    The Playwright objects are held live so we can use
    `context.request.post()` for replay (real Chrome TLS fingerprint +
    auto-rotating cookie jar). Caller is responsible for calling
    close_session() when done."""

    form: dict[str, str]              # parsed pagination POST body fields
    raw_body: str                     # exact captured body bytes (UTF-8)
    headers: dict[str, str]           # filtered replay headers
    url: str                          # the precise endpoint URL the browser hit
    cookies: list[dict]               # context.cookies() snapshot at harvest
    harvested_at: float               # time.monotonic() value
    friendly: str                     # debugging only
    # Live Playwright session — caller closes via close_session().
    pw: Any = None
    browser: Any = None
    context: Any = None
    page: Any = None


def close_session(tokens: Optional[TokenBundle]) -> None:
    """Idempotent teardown of the Playwright session held by a TokenBundle."""
    if tokens is None:
        return
    for attr in ("context", "browser"):
        obj = getattr(tokens, attr, None)
        if obj is None:
            continue
        try:
            obj.close()
        except Exception:
            pass
        setattr(tokens, attr, None)
    if tokens.pw is not None:
        try:
            tokens.pw.stop()
        except Exception:
            pass
        tokens.pw = None
    tokens.page = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_form_body(body: str) -> dict[str, str]:
    """Parse a urlencoded form body into a dict (last value wins on dups)."""
    out: dict[str, str] = {}
    for pair in body.split("&"):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        out[urllib.parse.unquote_plus(k)] = urllib.parse.unquote_plus(v)
    return out


def _pagination_priority(form: dict[str, str]) -> int:
    """Higher = better replay target. 0 = not pagination."""
    friendly = (form.get("fb_api_req_friendly_name") or "").lower()
    score = 0
    for needle, weight in _FRIENDLY_PRIORITY:
        if needle in friendly:
            score = max(score, weight)
    if score:
        return score
    raw_vars = form.get("variables")
    if not raw_vars:
        return 0
    try:
        v = json.loads(raw_vars)
    except Exception:
        return 0
    for key in ("cursor", "after", "endCursor", "afterTime", "beforeTime"):
        cv = v.get(key)
        if isinstance(cv, str) and len(cv) > 4:
            return 5
    return 0


def _build_form_body(template: dict[str, str], new_cursor: str) -> str:
    """Re-encode the captured form body with the cursor swapped in."""
    form = dict(template)
    try:
        variables = json.loads(form.get("variables", "{}"))
    except Exception:
        variables = {}
    variables["cursor"] = new_cursor
    form["variables"] = json.dumps(variables, separators=(",", ":"))
    # Bump __req so it isn't a literal byte-for-byte copy.
    try:
        form["__req"] = format(int(form.get("__req", "0"), 36) + 1, "x")
    except Exception:
        pass
    return urllib.parse.urlencode(form)


# ---------------------------------------------------------------------------
# Token harvest
# ---------------------------------------------------------------------------

def harvest_tokens(scraper, cfg, code: str, url: str,
                   logger=None) -> Optional[TokenBundle]:
    """Briefly drive a Playwright Chrome session to capture one pagination
    POST to /api/graphql/. Returns a TokenBundle with the browser kept alive
    for subsequent replay, or None on failure.

    The caller MUST call close_session(tokens) when done.

    `scraper` is a FacebookScraper instance — we reuse its
    _launch_desktop_session helper and _restore_session_state method so
    anti-detection flags and localStorage handling carry over identically.
    """
    from playwright.sync_api import sync_playwright

    log = logger or _NullLogger()

    captured_form: dict[str, str] = {}
    captured: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []
    seen_friendly: list[str] = []

    def on_request(request) -> None:
        try:
            if request.method != "POST":
                return
            if "/api/graphql" not in request.url:
                return
            body = request.post_data or ""
            if not body:
                return
            form = _parse_form_body(body)
            friendly = form.get("fb_api_req_friendly_name", "<no-name>")
            seen_friendly.append(friendly)
            priority = _pagination_priority(form)
            if priority <= 0:
                return
            try:
                # all_headers() returns the COMPLETE set Chrome sent
                # (including origin / sec-fetch-* / accept). Without it,
                # FB's WAF rejects with error 1357054.
                req_headers = dict(request.all_headers() or {})
            except Exception:
                try:
                    req_headers = dict(request.headers or {})
                except Exception:
                    req_headers = {}
            replay_headers = {
                k: v for k, v in req_headers.items()
                if not k.startswith(":")
                and k.lower() not in _REPLAY_HEADER_DENYLIST
            }
            candidates.append({
                "priority": priority,
                "form": form,
                "raw_body": body,
                "headers": replay_headers,
                "url": request.url,
                "friendly": friendly,
            })
        except Exception as exc:
            log.warning("[%s][graphql_httpx] on_request error: %s", code, exc)

    # Force non-persistent path so we control cookie injection. Persistent
    # profiles can carry stale auth; a clean context with fresh cookie
    # injection guarantees the page renders the authenticated feed (which
    # is what triggers pagination requests).
    saved_persistent = cfg.use_persistent_context
    cfg.use_persistent_context = False

    pw = sync_playwright().start()
    browser = None
    context = None
    page = None
    success = False
    try:
        browser, context = scraper._launch_desktop_session(pw, code)
        try:
            context.add_cookies(scraper._cookies)
            log.info("[%s][graphql_httpx] injected %d cookies",
                     code, len(scraper._cookies))
        except Exception as exc:
            log.warning("[%s][graphql_httpx] add_cookies failed: %s",
                        code, exc)

        pages = context.pages
        page = pages[0] if pages else context.new_page()
        page.on("request", on_request)

        page.set_default_timeout(cfg.graphql_httpx_harvest_timeout_seconds * 1000)
        page.goto(url, wait_until="domcontentloaded")
        try:
            scraper._restore_session_state(page)
        except Exception as exc:
            log.warning("[%s][graphql_httpx] restore_session_state: %s",
                        code, exc)

        # Trigger pagination: scroll until a Timeline-feed candidate
        # appears AND a brief observation window has elapsed. Without the
        # observation window a Tiles query (lower priority) wins the race.
        deadline = time.monotonic() + cfg.graphql_httpx_harvest_timeout_seconds
        min_observation_secs = 8
        scrolls = 0
        page.wait_for_timeout(3000)   # let initial feed render
        t_started = time.monotonic()
        while time.monotonic() < deadline:
            try:
                page.mouse.wheel(0, 6000)
            except Exception:
                pass
            if scrolls % 3 == 0:
                try:
                    page.keyboard.press("End")
                except Exception:
                    pass
            page.wait_for_timeout(1200)
            scrolls += 1
            top = max((c["priority"] for c in candidates), default=0)
            elapsed = time.monotonic() - t_started
            if top >= 80 and elapsed >= min_observation_secs:
                break
            if top > 0 and elapsed >= 20:
                break

        session_cookies = context.cookies()

        if not candidates:
            log.warning("[%s][graphql_httpx] harvest captured 0 candidates "
                        "after %d scrolls (%d graphql POSTs total) — "
                        "page may be unauthenticated or feed not rendered",
                        code, scrolls, len(seen_friendly))
            return None

        # Best = highest priority, ties broken by latest occurrence (freshest cursor).
        best = max(
            enumerate(candidates),
            key=lambda kv: (kv[1]["priority"], kv[0]),
        )[1]
        log.info("[%s][graphql_httpx] harvested tokens: friendly=%s "
                 "doc_id=%s (priority=%d, %d candidates seen)",
                 code, best["friendly"], best["form"].get("doc_id"),
                 best["priority"], len(candidates))

        success = True
        bundle = TokenBundle(
            form=best["form"],
            raw_body=best["raw_body"],
            headers=best["headers"],
            url=best["url"],
            cookies=session_cookies,
            harvested_at=time.monotonic(),
            friendly=best["friendly"],
            pw=pw,
            browser=browser,
            context=context,
            page=page,
        )
        return bundle
    finally:
        cfg.use_persistent_context = saved_persistent
        if not success:
            # Tear down on any failure path.
            try:
                if context is not None:
                    context.close()
            except Exception:
                pass
            try:
                if browser is not None:
                    browser.close()
            except Exception:
                pass
            try:
                pw.stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Replay loop
# ---------------------------------------------------------------------------

def should_refresh(tokens: TokenBundle, cfg) -> bool:
    """True if the bundle has aged past the proactive refresh threshold."""
    if tokens is None:
        return True
    age_secs = time.monotonic() - tokens.harvested_at
    return age_secs > cfg.graphql_httpx_token_refresh_minutes * 60


def paginate(scraper, cfg, code: str, tokens: TokenBundle,
             posts: list[dict], seen_hashes: set[str],
             start_cursor: Optional[str] = None,
             logger=None) -> tuple[list[dict], str, Optional[str]]:
    """Drive the captured pagination request via the kept-alive browser's
    APIRequestContext. Mutates `posts` and `seen_hashes` in place.

    Returns (posts, stop_reason, last_cursor) where stop_reason is one of:
      "target_reached", "end_of_feed", "token_expired",
      "max_errors", "max_iterations", "killed".

    `last_cursor` is the cursor most recently advanced to — pass it back as
    `start_cursor` after a re-harvest so we resume from where we left off
    instead of fast-forwarding through every previously-collected post.
    Pass start_cursor=None on the first call (uses the cursor captured in
    tokens.form).

    Persists JSONL via scraper._checkpoint_save() at the same cadence as
    the desktop strategy (every 30s when new posts arrive).
    """
    # Late-import to avoid circular dep: scraper.py imports this module
    # only inside the strategy method.
    from scraper import _GraphQLPostExtractor

    log = logger or _NullLogger()

    page = tokens.page
    context = tokens.context
    if page is None or context is None:
        return posts, "killed", start_cursor

    api = context.request

    headers = dict(tokens.headers)
    headers.setdefault("content-type", "application/x-www-form-urlencoded")
    url = tokens.url

    # Cursor selection: prefer the caller-provided start_cursor (resume
    # from where the previous session left off across a token refresh),
    # otherwise fall back to the cursor captured in tokens.form (first
    # call from a freshly-harvested session).
    cursor = start_cursor
    if not cursor:
        try:
            cursor = json.loads(tokens.form.get("variables", "{}")).get("cursor")
        except Exception:
            cursor = None
    if not cursor:
        log.warning("[%s][graphql_httpx] no cursor available — cannot paginate", code)
        return posts, "end_of_feed", None
    if start_cursor:
        log.info("[%s][graphql_httpx] resuming with preserved cursor (len=%d) — "
                 "skipping fast-forward", code, len(cursor))

    consecutive_errors = 0
    last_checkpoint_t = time.monotonic()
    iterations = 0
    target = cfg.target_posts

    while iterations < cfg.graphql_httpx_max_iterations:
        iterations += 1

        # Token age check — caller will re-harvest after we return.
        if should_refresh(tokens, cfg):
            log.info("[%s][graphql_httpx] tokens aged out (%.1f min) — "
                     "signaling caller to re-harvest",
                     code, (time.monotonic() - tokens.harvested_at) / 60)
            return posts, "token_expired", cursor

        body = _build_form_body(tokens.form, cursor)
        try:
            resp = api.post(url, data=body, headers=headers, timeout=30000)
        except Exception as exc:
            consecutive_errors += 1
            log.warning("[%s][graphql_httpx] iter=%d post error: %s",
                        code, iterations, exc)
            if consecutive_errors >= cfg.graphql_httpx_max_consecutive_errors:
                return posts, "max_errors", cursor
            time.sleep(2.0 * consecutive_errors)
            continue

        status = resp.status
        if status != 200:
            consecutive_errors += 1
            log.warning("[%s][graphql_httpx] iter=%d HTTP %d",
                        code, iterations, status)
            # 401/403 strongly suggest token expiry — bail to caller
            # for re-harvest.
            if status in (401, 403):
                return posts, "token_expired", cursor
            if consecutive_errors >= cfg.graphql_httpx_max_consecutive_errors:
                return posts, "max_errors", cursor
            time.sleep(2.0 * consecutive_errors)
            continue

        body_bytes = resp.body() or b""
        if body_bytes.startswith(b"for (;;);"):
            body_bytes = body_bytes[len(b"for (;;);"):]
        if not body_bytes.strip():
            consecutive_errors += 1
            if consecutive_errors >= cfg.graphql_httpx_max_consecutive_errors:
                return posts, "max_errors", cursor
            continue

        # Detect the FB error envelope ("error":1357054 etc.) which arrives
        # as HTTP 200 but is really a session/CSRF rejection.
        if b'"error":' in body_bytes[:200] and b'"errorSummary"' in body_bytes[:400]:
            try:
                env = json.loads(body_bytes.decode("utf-8", errors="replace"))
                err = env.get("errorSummary") or env.get("errorDescription")
            except Exception:
                err = "unparseable error envelope"
            log.warning("[%s][graphql_httpx] iter=%d FB error envelope: %s",
                        code, iterations, err)
            return posts, "token_expired", cursor

        # Reset error streak on a structurally-valid response.
        consecutive_errors = 0

        new_cursor: Optional[str] = None
        new_count = 0
        for chunk in _GraphQLPostExtractor._iter_json_chunks(body_bytes):
            if isinstance(chunk, dict) and chunk.get("errors"):
                errs = chunk["errors"]
                err_blob = json.dumps(errs).lower()
                log.warning("[%s][graphql_httpx] iter=%d graphql errors: %s",
                            code, iterations,
                            json.dumps(errs)[:300])
                # Distinguish rate limiting from token expiry. Re-harvesting
                # on a rate limit makes things worse (more requests against
                # an already-over-limit account); the only safe response is
                # to stop and let the user wait it out.
                if (
                    '"code": 1675004' in err_blob
                    or '"code":1675004' in err_blob
                    or "rate limit" in err_blob
                    or "rate_limit" in err_blob
                    or "throttled" in err_blob
                ):
                    log.error("[%s][graphql_httpx] RATE LIMITED by Facebook "
                              "(code 1675004 / 'Rate limit exceeded'). "
                              "Stopping cleanly — DO NOT re-run for at least "
                              "1 hour. JSONL preserved at data/%s.jsonl.",
                              code, code)
                    return posts, "rate_limited", cursor
                # Other graphql errors are typically auth/CSRF — re-harvest.
                return posts, "token_expired", cursor
            for c in _GraphQLPostExtractor._walk_for_cursors(chunk):
                new_cursor = c
            for post in _GraphQLPostExtractor._walk_for_stories(chunk):
                text = post.get("text") or ""
                if not text:
                    continue
                h = post_hash(text)
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                posts.append(post)
                new_count += 1

        if iterations % 10 == 0 or new_count > 0:
            log.info("[%s][graphql_httpx] iter=%d total=%d (+%d) "
                     "next_cursor=%s",
                     code, iterations, len(posts), new_count,
                     (new_cursor or "")[:24])

        # Stop conditions.
        if len(posts) >= target:
            return posts, "target_reached", new_cursor or cursor
        if not new_cursor or new_cursor == cursor:
            log.info("[%s][graphql_httpx] end-of-feed at iter=%d "
                     "(cursor unchanged) total=%d",
                     code, iterations, len(posts))
            return posts, "end_of_feed", cursor
        cursor = new_cursor

        # Time-debounced checkpoint (mirrors desktop strategy cadence).
        if new_count > 0:
            now = time.monotonic()
            if now - last_checkpoint_t >= 30:
                try:
                    scraper._checkpoint_save(posts, code)
                    last_checkpoint_t = now
                    log.info("[%s][graphql_httpx] checkpoint: %d/%d posts",
                             code, len(posts), target)
                except Exception as exc:
                    log.warning("[%s][graphql_httpx] checkpoint save: %s",
                                code, exc)

        random_sleep(cfg.graphql_httpx_request_delay_min,
                     cfg.graphql_httpx_request_delay_max)

    return posts, "max_iterations", cursor


# ---------------------------------------------------------------------------
# Fallback logger for unit-testing without the scraper
# ---------------------------------------------------------------------------

class _NullLogger:
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def error(self, *a, **kw): pass
    def debug(self, *a, **kw): pass
