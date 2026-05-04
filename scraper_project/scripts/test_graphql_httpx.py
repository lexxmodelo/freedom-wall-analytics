"""
Phase 1 proof-of-concept for the desktop_graphql_httpx strategy.

Validates the technique against live Facebook BEFORE touching the production
scraper:
  1. Load cookies via the existing FacebookScraper machinery.
  2. Launch a single Playwright Chrome page; navigate to the target.
  3. Hook page.on("request") and page.on("response") to capture the first
     pagination POST to /api/graphql/. Snapshot fb_dtsg, lsd, jazoest,
     doc_id, variables, headers, and the end_cursor returned by the response.
  4. Close Chrome.
  5. Build an httpx.Client and replay the pagination request, mutating only
     `variables.cursor` between calls. Parse responses with the existing
     _GraphQLPostExtractor static methods.
  6. Stop after --max-posts unique posts or --max-iterations.
  7. Report wall time, peak RSS, posts collected, and any error shape.

Pass criteria (per plan):
  - Exit code 0
  - >= 50 unique posts in stdout summary
  - Peak RSS < 200 MB
  - Wall time < 60 s
  - No HTTP errors, no GraphQL errors[] in responses

Usage:
    python scripts/test_graphql_httpx.py --target SLU --max-posts 50

Run from the scraper_project/ directory so relative imports resolve.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from typing import Any, Optional

# Make the parent directory importable when invoked as `python scripts/...`
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(_HERE)
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from config import ScraperConfig, TARGETS  # noqa: E402
from scraper import FacebookScraper, _GraphQLPostExtractor  # noqa: E402
from utils import post_hash, random_sleep  # noqa: E402


# ---------------------------------------------------------------------------
# Memory measurement
# ---------------------------------------------------------------------------

def _rss_mb() -> float:
    """Resident-set size of this Python process, in MB. Returns 0 if psutil
    is unavailable (graceful — measurement is for reporting only)."""
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Token harvest
# ---------------------------------------------------------------------------

# Form-field names we want from any graphql POST body.
_TOKEN_FIELDS = (
    "fb_dtsg",
    "lsd",
    "jazoest",
    "doc_id",
    "fb_api_req_friendly_name",
    "fb_api_caller_class",
    "variables",
    "server_timestamps",
    "av",
    "__user",
    "__a",
    "__req",
    "__hs",
    "__rev",
    "dpr",
    "__ccg",
    "__comet_req",
)

# Headers worth replaying. Many of these are required for FB to accept the
# POST; we replay everything the browser sent except hop-by-hop headers and
# anything that httpx will manage itself (host, content-length, cookie).
_REPLAY_HEADER_DENYLIST = {
    "host",
    "content-length",
    "cookie",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "accept-encoding",  # let httpx negotiate its own
}


def _parse_form_body(body: str) -> dict[str, str]:
    """Parse a urlencoded form body into a dict. Multi-valued keys keep the
    last occurrence (FB graphql POSTs do not use repeated keys)."""
    out: dict[str, str] = {}
    for pair in body.split("&"):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        out[urllib.parse.unquote_plus(k)] = urllib.parse.unquote_plus(v)
    return out


# Priority list — higher is better. Timeline-feed queries return the actual
# wall posts we want; Tiles queries return the photo grid (no message text).
_FRIENDLY_PRIORITY = [
    ("profilecomettimelinefeed", 100),   # the wall feed itself
    ("comettimelinefeed",         90),
    ("timelinefeed",              80),
    ("timeline",                  60),
    ("comet" + "feed",            50),
    ("feedpagination",            40),
    ("pagefeed",                  35),
    ("pagination",                10),   # generic — last resort
    ("tiles",                      1),   # photo grid — better than nothing
]


def _pagination_priority(form: dict[str, str]) -> int:
    """Return a priority score for this graphql POST as a pagination
    candidate. 0 = not a pagination request. Higher = better target for
    replay (timeline feed > tiles > random feeds)."""
    friendly = (form.get("fb_api_req_friendly_name") or "").lower()
    score = 0
    for needle, weight in _FRIENDLY_PRIORITY:
        if needle in friendly:
            score = max(score, weight)
    if score:
        return score

    # No friendly-name match — check for cursor in variables as fallback.
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


def _is_pagination_request(form: dict[str, str]) -> bool:
    """Backward-compat predicate for log lines."""
    return _pagination_priority(form) > 0


def harvest_tokens(scraper: FacebookScraper, url: str, target_code: str,
                   harvest_scrolls: int, timeout_secs: int,
                   keep_alive: bool = False
                   ) -> Optional[dict]:
    """Launch Chrome, navigate, scroll, capture the first pagination POST.

    If keep_alive=True, the browser/context/page are returned in the dict
    under keys "_pw"/"_browser"/"_context"/"_page" and NOT closed by this
    function — the caller must close them. This enables in-browser replay
    (page.request.post) which inherits real Chrome TLS fingerprint and
    auto-refreshes fb_dtsg via the cookie jar.

    Returns a dict ready to feed the replay loop, or None on failure.
    """
    from playwright.sync_api import sync_playwright

    # `captured` is the final selection; `candidates` is everything observed
    # during the harvest window. We pick the highest-priority candidate at
    # the end (so a Tiles query doesn't win the race against the slightly-
    # later TimelineFeed query we actually want).
    captured: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []
    seen_friendly: list[str] = []  # for debug — what queries did we see?
    all_request_count = [0]
    sample_urls: list[str] = []

    def on_any_request(request) -> None:
        all_request_count[0] += 1
        # Capture URL samples to verify event firing + see what FB is loading.
        if all_request_count[0] <= 30 or "graphql" in request.url.lower() \
                or "/api/" in request.url.lower():
            sample_urls.append(f"{request.method} {request.url[:120]}")

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
            print(f"[harvest:rx] graphql POST friendly={friendly!r} "
                  f"priority={priority} doc_id={form.get('doc_id')}")
            if priority <= 0:
                return
            # Snapshot the COMPLETE set of headers Chrome actually sent.
            # request.headers misses headers added by the network stack
            # (origin, sec-fetch-*, accept) — request.all_headers() returns
            # the full set. all_headers() is async on most bindings but
            # works synchronously in Playwright Python's sync API.
            try:
                req_headers = dict(request.all_headers() or {})
            except Exception:
                try:
                    req_headers = dict(request.headers or {})
                except Exception:
                    req_headers = {}
            replay_headers = {
                k: v for k, v in req_headers.items()
                # Drop hop-by-hop, drop HTTP/2 pseudo-headers (start with :),
                # drop ones the HTTP client manages itself.
                if not k.startswith(":")
                and k.lower() not in _REPLAY_HEADER_DENYLIST
            }
            candidates.append({
                "priority": priority,
                "form": form,
                "raw_body": body,           # exact bytes the browser sent
                "headers": replay_headers,
                "url": request.url,
                "friendly": friendly,
            })
        except Exception as exc:
            print(f"[harvest] on_request error: {exc}", file=sys.stderr)

    # Force the non-persistent path so we control cookie injection. The
    # persistent profile dir may carry stale auth from earlier runs, which
    # leaves the page in a logged-out state and FB never issues pagination
    # requests.
    scraper.cfg.use_persistent_context = False

    # We can't use a `with sync_playwright() as pw` block when keep_alive=True
    # because the caller needs the browser to remain open for replay; manual
    # start/stop instead.
    pw = sync_playwright().start()
    browser = None
    context = None
    page = None
    success = False

    try:
        browser, context = scraper._launch_desktop_session(pw, target_code)

        # Belt-and-suspenders: inject cookies regardless of which branch
        # the launcher took. _launch_desktop_session only calls add_cookies
        # on its fresh-fallback paths, not on a happy-path persistent
        # context launch — and persistent profile dirs go stale.
        try:
            context.add_cookies(scraper._cookies)
            print(f"[harvest] injected {len(scraper._cookies)} cookies "
                  f"into context")
        except Exception as exc:
            print(f"[harvest] add_cookies failed: {exc}", file=sys.stderr)

        pages = context.pages
        page = pages[0] if pages else context.new_page()
        page.on("request", on_any_request)
        page.on("request", on_request)

        page.set_default_timeout(timeout_secs * 1000)
        page.goto(url, wait_until="domcontentloaded")
        try:
            scraper._restore_session_state(page)
        except Exception as exc:
            print(f"[harvest] restore_session_state failed: {exc}",
                  file=sys.stderr)

        session_cookies = context.cookies()

        # Trigger pagination: scroll until we have a Timeline-feed candidate
        # AND a brief observation window has elapsed (so a slightly-later
        # better request can win).
        deadline = time.monotonic() + timeout_secs
        min_observation_secs = 8
        scrolls = 0
        page.wait_for_timeout(3000)        # let initial feed render
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
            if scrolls % 5 == 0:
                top_now = max((c["priority"] for c in candidates), default=0)
                print(f"[harvest] scrolled {scrolls}x; graphql POSTs seen: "
                      f"{len(seen_friendly)}; candidates: {len(candidates)} "
                      f"(top priority={top_now})", flush=True)
            top = max((c["priority"] for c in candidates), default=0)
            elapsed = time.monotonic() - t_started
            if top >= 80 and elapsed >= min_observation_secs:
                break
            if top > 0 and elapsed >= 20:
                break

        if candidates:
            # Among equal-priority candidates, prefer the latest (freshest
            # cursor — earlier ones are stale by the time we replay).
            best = max(
                enumerate(candidates),
                key=lambda kv: (kv[1]["priority"], kv[0]),
            )[1]
            captured["form"] = best["form"]
            captured["raw_body"] = best["raw_body"]
            captured["headers"] = best["headers"]
            captured["url"] = best["url"]
            print(f"[harvest] CAPTURED best candidate: "
                  f"priority={best['priority']} "
                  f"friendly={best['friendly']} "
                  f"doc_id={best['form'].get('doc_id')}")
        else:
            print(f"[harvest] timed out after {scrolls} scrolls. "
                  f"Saw {len(seen_friendly)} graphql POSTs out of "
                  f"{all_request_count[0]} total requests.",
                  file=sys.stderr)
            try:
                print(f"[harvest] page url: {page.url}", file=sys.stderr)
                print(f"[harvest] page title: {page.title()}",
                      file=sys.stderr)
            except Exception:
                pass
            ss_path = os.path.join(_PROJ, "scripts",
                                   "_poc_harvest_fail.png")
            try:
                page.screenshot(path=ss_path, full_page=False)
                print(f"[harvest] screenshot saved: {ss_path}",
                      file=sys.stderr)
            except Exception as exc:
                print(f"[harvest] screenshot failed: {exc}",
                      file=sys.stderr)
            print("[harvest] first request URL samples:", file=sys.stderr)
            for s in sample_urls[:30]:
                print(f"  {s}", file=sys.stderr)
            from collections import Counter
            if seen_friendly:
                print("[harvest] graphql friendly_name histogram:",
                      file=sys.stderr)
                for name, n in Counter(seen_friendly).most_common():
                    print(f"  {n:3d}x  {name}", file=sys.stderr)
            return None

        captured["cookies"] = session_cookies
        captured["harvested_at"] = time.monotonic()
        success = True
        if keep_alive:
            # Hand the live session to the caller so the replay loop can
            # use page.request.post() — inherits real-Chrome TLS
            # fingerprint, auto-refreshes fb_dtsg via the cookie jar, and
            # avoids DOM rendering (no memory cliff because we never scroll
            # again).
            captured["_pw"] = pw
            captured["_browser"] = browser
            captured["_context"] = context
            captured["_page"] = page
            return captured
        return captured
    finally:
        if not (success and keep_alive):
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
# httpx replay loop
# ---------------------------------------------------------------------------

def _cookies_to_httpx(playwright_cookies: list[dict]):
    """Independent of FacebookScraper._cookies_to_httpx so the PoC can use
    cookies harvested at runtime (which include FB-issued refreshes)."""
    import httpx
    jar = httpx.Cookies()
    for c in playwright_cookies:
        domain = c.get("domain", "")
        if "facebook.com" not in domain:
            continue
        jar.set(
            c["name"], c["value"],
            domain=domain.lstrip("."),
            path=c.get("path", "/"),
        )
    return jar


def _build_form_body(template: dict[str, str], new_cursor: str) -> str:
    """Re-encode the form body with the cursor swapped in."""
    form = dict(template)
    try:
        variables = json.loads(form.get("variables", "{}"))
    except Exception:
        variables = {}
    variables["cursor"] = new_cursor
    form["variables"] = json.dumps(variables, separators=(",", ":"))
    # Bump __req so it's not a literal copy of the harvested request.
    try:
        form["__req"] = format(int(form.get("__req", "0"), 36) + 1, "x")
    except Exception:
        pass
    return urllib.parse.urlencode(form)


def replay_loop(captured: dict, max_posts: int, max_iterations: int,
                request_delay_min: float, request_delay_max: float
                ) -> tuple[list[dict], dict[str, Any]]:
    """Drive the captured pagination request via httpx until max_posts or
    max_iterations. Returns (posts, telemetry)."""
    import httpx

    headers = dict(captured["headers"])
    cookies = _cookies_to_httpx(captured["cookies"])
    # Use the EXACT URL the browser used. FB's WAF is sensitive to query
    # parameters on /api/graphql/ — replay to the literal endpoint the
    # browser hit. Falls back to the bare path if the capture is malformed.
    url = captured.get("url") or "https://www.facebook.com/api/graphql/"
    print(f"[replay] target url: {url}")

    print(f"[replay] {len(headers)} headers, {len(cookies)} cookies. "
          f"Headers: {sorted(headers.keys())}")

    seen: set[str] = set()
    posts: list[dict] = []
    telemetry: dict[str, Any] = {
        "iterations": 0,
        "errors": [],
        "http_status_codes": [],
        "graphql_error_count": 0,
        "empty_response_count": 0,
        "peak_rss_mb": _rss_mb(),
    }

    # Initial cursor: take whatever the harvested request itself carries.
    try:
        cursor = json.loads(captured["form"].get("variables", "{}")).get("cursor")
    except Exception:
        cursor = None
    if not cursor:
        telemetry["errors"].append("no initial cursor in harvested form")
        return posts, telemetry

    with httpx.Client(
        cookies=cookies, headers=headers,
        follow_redirects=False, timeout=30.0, http2=False,
    ) as client:
        for it in range(max_iterations):
            telemetry["iterations"] = it + 1
            # First iteration: replay the EXACT captured body verbatim, to
            # isolate whether the mutation logic is the problem vs. headers /
            # cookies / encoding. Subsequent iterations swap the cursor.
            if it == 0 and captured.get("raw_body"):
                body = captured["raw_body"]
                print(f"[replay] iter=01 replaying raw captured body "
                      f"({len(body)} bytes, no mutation)")
            else:
                body = _build_form_body(captured["form"], cursor)
            try:
                resp = client.post(
                    url, content=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            except Exception as exc:
                telemetry["errors"].append(f"httpx error iter={it}: {exc}")
                break

            telemetry["http_status_codes"].append(resp.status_code)
            telemetry["peak_rss_mb"] = max(telemetry["peak_rss_mb"], _rss_mb())

            # Debug: dump first response so we can see the shape FB returns.
            if it == 0:
                _dbg_path = os.path.join(_PROJ, "scripts",
                                         "_poc_first_response.bin")
                try:
                    with open(_dbg_path, "wb") as _f:
                        _f.write(resp.content)
                    print(f"[replay:dbg] saved first response to {_dbg_path} "
                          f"({len(resp.content)} bytes)")
                except Exception:
                    pass

            if resp.status_code != 200:
                telemetry["errors"].append(
                    f"HTTP {resp.status_code} iter={it} "
                    f"body_preview={resp.text[:200]!r}"
                )
                break

            body_bytes = resp.content
            if not body_bytes:
                telemetry["empty_response_count"] += 1
                break

            # Facebook's anti-CSRF prefix: responses begin with "for (;;);"
            # to break naive JSON.parse() in browsers. Strip before parsing.
            if body_bytes.startswith(b"for (;;);"):
                body_bytes = body_bytes[len(b"for (;;);"):]

            # Reuse the existing parsers — they're @staticmethod.
            new_posts_this_iter = 0
            new_cursor: Optional[str] = None
            for chunk in _GraphQLPostExtractor._iter_json_chunks(body_bytes):
                # Detect GraphQL-level errors anywhere in the response tree.
                if isinstance(chunk, dict) and chunk.get("errors"):
                    telemetry["graphql_error_count"] += 1
                    telemetry["errors"].append(
                        f"graphql errors iter={it}: "
                        f"{json.dumps(chunk['errors'])[:300]}"
                    )

                # Cursors first.
                for c in _GraphQLPostExtractor._walk_for_cursors(chunk):
                    new_cursor = c

                # Then stories.
                for post in _GraphQLPostExtractor._walk_for_stories(chunk):
                    text = post.get("text") or ""
                    if not text:
                        continue
                    h = post_hash(text)
                    if h in seen:
                        continue
                    seen.add(h)
                    posts.append(post)
                    new_posts_this_iter += 1
                    if len(posts) >= max_posts:
                        break

            print(
                f"[replay] iter={it+1:02d} status={resp.status_code} "
                f"new={new_posts_this_iter} total={len(posts)} "
                f"rss={telemetry['peak_rss_mb']:.0f}MB "
                f"next_cursor={(new_cursor or '')[:24]}..."
            )

            if telemetry["graphql_error_count"]:
                break
            if len(posts) >= max_posts:
                break
            if not new_cursor or new_cursor == cursor:
                telemetry["errors"].append(
                    f"end-of-feed at iter={it} (cursor unchanged)"
                )
                break
            cursor = new_cursor
            random_sleep(request_delay_min, request_delay_max)

    return posts, telemetry


# ---------------------------------------------------------------------------
# Playwright-context replay (uses real Chrome's HTTP stack)
# ---------------------------------------------------------------------------

def replay_loop_playwright(captured: dict, max_posts: int,
                           max_iterations: int,
                           request_delay_min: float,
                           request_delay_max: float
                           ) -> tuple[list[dict], dict[str, Any]]:
    """Replay via Playwright's APIRequestContext, which uses the same Chrome
    HTTP stack that minted the cookies/fb_dtsg. Inherits TLS fingerprint,
    auto-applies cookie jar (so fr/datr rotations carry over), and avoids
    the JA3-fingerprint problem that breaks raw httpx replay.

    No further DOM rendering happens — we never scroll the page again — so
    memory remains bounded. The browser is just an HTTP client at this
    point."""
    page = captured["_page"]
    context = captured["_context"]
    api = context.request  # APIRequestContext bound to the context

    headers = dict(captured["headers"])
    # Always set Content-Type for form posts.
    headers.setdefault("content-type", "application/x-www-form-urlencoded")
    # Use the EXACT URL the browser used. FB's WAF is sensitive to query
    # parameters on /api/graphql/ — replay to the literal endpoint the
    # browser hit. Falls back to the bare path if the capture is malformed.
    url = captured.get("url") or "https://www.facebook.com/api/graphql/"
    print(f"[replay] target url: {url}")

    print(f"[replay-pw] {len(headers)} replay headers")

    seen: set[str] = set()
    posts: list[dict] = []
    telemetry: dict[str, Any] = {
        "iterations": 0,
        "errors": [],
        "http_status_codes": [],
        "graphql_error_count": 0,
        "empty_response_count": 0,
        "peak_rss_mb": _rss_mb(),
    }

    try:
        cursor = json.loads(captured["form"].get("variables", "{}")).get("cursor")
    except Exception:
        cursor = None
    if not cursor:
        telemetry["errors"].append("no initial cursor in harvested form")
        return posts, telemetry

    for it in range(max_iterations):
        telemetry["iterations"] = it + 1
        # First iteration: replay raw captured body verbatim, to validate
        # the pipeline before any mutation.
        if it == 0 and captured.get("raw_body"):
            body = captured["raw_body"]
        else:
            body = _build_form_body(captured["form"], cursor)

        try:
            resp = api.post(url, data=body, headers=headers, timeout=30000)
        except Exception as exc:
            telemetry["errors"].append(f"playwright post error iter={it}: {exc}")
            break

        status = resp.status
        telemetry["http_status_codes"].append(status)
        telemetry["peak_rss_mb"] = max(telemetry["peak_rss_mb"], _rss_mb())

        body_bytes = resp.body() or b""
        if it == 0:
            _dbg_path = os.path.join(_PROJ, "scripts",
                                     "_poc_first_response.bin")
            try:
                with open(_dbg_path, "wb") as _f:
                    _f.write(body_bytes)
                print(f"[replay-pw:dbg] saved first response "
                      f"({len(body_bytes)} bytes) status={status}")
            except Exception:
                pass

        if status != 200:
            telemetry["errors"].append(
                f"HTTP {status} iter={it} body_preview="
                f"{body_bytes[:200].decode('utf-8', errors='replace')!r}"
            )
            break

        # Strip FB's anti-CSRF prefix.
        if body_bytes.startswith(b"for (;;);"):
            body_bytes = body_bytes[len(b"for (;;);"):]
        if not body_bytes.strip():
            telemetry["empty_response_count"] += 1
            break

        new_posts_this_iter = 0
        new_cursor: Optional[str] = None
        for chunk in _GraphQLPostExtractor._iter_json_chunks(body_bytes):
            if isinstance(chunk, dict) and chunk.get("errors"):
                telemetry["graphql_error_count"] += 1
                telemetry["errors"].append(
                    f"graphql errors iter={it}: "
                    f"{json.dumps(chunk['errors'])[:300]}"
                )
            for c in _GraphQLPostExtractor._walk_for_cursors(chunk):
                new_cursor = c
            for post in _GraphQLPostExtractor._walk_for_stories(chunk):
                text = post.get("text") or ""
                if not text:
                    continue
                h = post_hash(text)
                if h in seen:
                    continue
                seen.add(h)
                posts.append(post)
                new_posts_this_iter += 1
                if len(posts) >= max_posts:
                    break

        print(
            f"[replay-pw] iter={it+1:02d} status={status} "
            f"new={new_posts_this_iter} total={len(posts)} "
            f"rss={telemetry['peak_rss_mb']:.0f}MB "
            f"next_cursor={(new_cursor or '')[:24]}..."
        )

        if telemetry["graphql_error_count"]:
            break
        if len(posts) >= max_posts:
            break
        if not new_cursor or new_cursor == cursor:
            telemetry["errors"].append(
                f"end-of-feed at iter={it} (cursor unchanged)"
            )
            break
        cursor = new_cursor
        random_sleep(request_delay_min, request_delay_max)

    return posts, telemetry


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", default="SLU",
                   help="Target code from config.TARGETS (default: SLU)")
    p.add_argument("--max-posts", type=int, default=50)
    p.add_argument("--max-iterations", type=int, default=10)
    p.add_argument("--cookie-file", default="cookies.json")
    p.add_argument("--harvest-scrolls", type=int, default=2)
    p.add_argument("--harvest-timeout", type=int, default=30,
                   help="Seconds to wait while harvesting tokens")
    p.add_argument("--request-delay-min", type=float, default=2.0)
    p.add_argument("--request-delay-max", type=float, default=5.0)
    p.add_argument("--headed", action="store_true",
                   help="Show the browser during the harvest phase")
    p.add_argument("--replay-mode", default="playwright",
                   choices=["playwright", "httpx"],
                   help="playwright = use real Chrome's HTTP stack via "
                        "page.context.request (recommended); "
                        "httpx = raw httpx (fails on TLS fingerprint)")
    args = p.parse_args()

    # Resolve target URL.
    target = next((t for t in TARGETS if t["code"] == args.target), None)
    if not target:
        print(f"[error] unknown target code {args.target!r}; "
              f"valid codes: {[t['code'] for t in TARGETS]}", file=sys.stderr)
        return 2

    # Build a config with the cookie file resolved relative to the project root.
    cookie_path = args.cookie_file
    if not os.path.isabs(cookie_path):
        cookie_path = os.path.join(_PROJ, cookie_path)
    if not os.path.exists(cookie_path):
        print(f"[error] cookie file not found: {cookie_path}", file=sys.stderr)
        return 2

    cfg = ScraperConfig(
        cookie_file=cookie_path,
        headless=not args.headed,
        headed=args.headed,
    )
    scraper = FacebookScraper(cfg)
    if not scraper._cookies:
        print("[error] no cookies loaded; aborting", file=sys.stderr)
        return 2

    print(f"[poc] target={args.target} url={target['url']}")
    print(f"[poc] cookies={len(scraper._cookies)} "
          f"localStorage_keys={len(scraper._session_state.get('localStorage', {}))}")
    print(f"[poc] starting RSS={_rss_mb():.0f}MB")

    t0 = time.monotonic()

    # Phase A — harvest. keep_alive only needed for playwright replay mode.
    keep_alive = (args.replay_mode == "playwright")
    captured = harvest_tokens(
        scraper, target["url"], args.target,
        args.harvest_scrolls, args.harvest_timeout,
        keep_alive=keep_alive,
    )
    if not captured:
        print("[poc] harvest FAILED", file=sys.stderr)
        return 1
    t_harvest = time.monotonic() - t0
    print(f"[poc] harvest complete in {t_harvest:.1f}s; RSS={_rss_mb():.0f}MB")

    # Phase B — replay.
    try:
        if args.replay_mode == "playwright":
            posts, telemetry = replay_loop_playwright(
                captured,
                max_posts=args.max_posts,
                max_iterations=args.max_iterations,
                request_delay_min=args.request_delay_min,
                request_delay_max=args.request_delay_max,
            )
        else:
            posts, telemetry = replay_loop(
                captured,
                max_posts=args.max_posts,
                max_iterations=args.max_iterations,
                request_delay_min=args.request_delay_min,
                request_delay_max=args.request_delay_max,
            )
    finally:
        # Tear down kept-alive Playwright session if present.
        for k in ("_context", "_browser"):
            obj = captured.get(k)
            if obj is None:
                continue
            try:
                obj.close()
            except Exception:
                pass
        pw = captured.get("_pw")
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass
    t_total = time.monotonic() - t0

    # Report.
    print()
    print("=" * 70)
    print(f"  TARGET:           {args.target} ({target['url']})")
    print(f"  POSTS COLLECTED:  {len(posts)} unique")
    print(f"  ITERATIONS:       {telemetry['iterations']}")
    print(f"  HTTP STATUSES:    {telemetry['http_status_codes']}")
    print(f"  GRAPHQL ERRORS:   {telemetry['graphql_error_count']}")
    print(f"  EMPTY RESPONSES:  {telemetry['empty_response_count']}")
    print(f"  PEAK RSS:         {telemetry['peak_rss_mb']:.0f} MB")
    print(f"  HARVEST TIME:     {t_harvest:.1f} s")
    print(f"  TOTAL TIME:       {t_total:.1f} s")
    if telemetry["errors"]:
        print("  ERRORS:")
        for e in telemetry["errors"]:
            print(f"    - {e}")
    print("=" * 70)

    # Pass-criteria gate (per plan Phase 3a).
    ok = (
        len(posts) >= args.max_posts
        and telemetry["peak_rss_mb"] < 200
        and t_total < 60
        and telemetry["graphql_error_count"] == 0
        and all(s == 200 for s in telemetry["http_status_codes"])
    )
    if ok:
        print("[poc] PASS — all phase 3a criteria met")
        return 0
    print("[poc] FAIL — see report above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
