"""
Playwright-based Facebook scraping engine (sync API).

Two strategies:
  1. Desktop  — www.facebook.com  (full JS rendering)
  2. Basic Mobile — mbasic.facebook.com (minimal JS, simpler DOM)

Supports optional cookie-based authentication for full-depth scraping.
Uses Playwright sync API for Python 3.14 compatibility.
"""

import ctypes
import json
import logging
import os
import random
import threading
import time
from typing import Optional

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, TimeoutError as PWTimeoutError
from tqdm import tqdm

from config import ScraperConfig
from parser import DesktopHTMLParser, DesktopParser, BasicMobileParser
from utils import random_sleep, deduplicate_posts, post_hash

logger = logging.getLogger("fw_scraper")


# Re-injected on every fresh page (initial launch + every session restart).
NAV_WEBDRIVER_OVERRIDE = (
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
)

# Pre-freeze diagnostic: capture screenshot if a single scroll dwells beyond this.
SAME_SCROLL_DWELL_SECS = 30.0


class _GraphQLPostExtractor:
    """Passive collector that scrapes Facebook posts directly from intercepted
    GraphQL responses on /api/graphql/ — bypassing the DOM entirely.

    Why: DOM extraction freezes Chrome past ~200 scrolls due to V8 heap
    fragmentation and React reconciliation cascades. Network interception is
    immune to DOM size because it reads bodies as they arrive and discards
    everything else.

    Attach once per page (re-attach after every session restart). The extractor
    shares its dedupe set with the caller so DOM and GraphQL paths cannot
    double-count the same post.
    """

    def __init__(self, dedupe_keys: set, seen_cursors: Optional[set] = None):
        self._posts: list[dict] = []
        self._seen = dedupe_keys              # SHARED with main loop
        self._cursors: set[str] = seen_cursors if seen_cursors is not None else set()
        self.latest_cursor: Optional[str] = None
        self.cursors_seen_this_session: list[str] = []
        self.responses_seen = 0
        self.bytes_seen = 0
        self._handler = None

    def attach(self, page) -> None:
        if self._handler is not None:
            return
        self._handler = self._on_response
        try:
            page.on("response", self._handler)
        except Exception as exc:
            logger.warning("GraphQL extractor attach failed: %s", exc)
            self._handler = None

    def detach(self, page) -> None:
        if self._handler is None:
            return
        try:
            page.remove_listener("response", self._handler)
        except Exception:
            pass
        self._handler = None

    def drain(self) -> list[dict]:
        out, self._posts = self._posts, []
        return out

    # ---- internals ----------------------------------------------------------

    def _on_response(self, resp) -> None:
        try:
            url = resp.url or ""
        except Exception:
            return
        if "/api/graphql" not in url:
            return
        try:
            body = resp.body()
        except Exception:
            return
        if not body:
            return
        self.bytes_seen += len(body)
        self.responses_seen += 1
        for chunk in self._iter_json_chunks(body):
            # Harvest cursors regardless of whether posts are extracted.
            # We use cursors to detect when we've crossed the seen-content
            # boundary on restart — a cursor not in self._cursors means
            # Facebook is now serving content past where we last looked.
            for cursor in self._walk_for_cursors(chunk):
                if cursor and cursor not in self._cursors:
                    self._cursors.add(cursor)
                    self.cursors_seen_this_session.append(cursor)
                    self.latest_cursor = cursor

            for post in self._walk_for_stories(chunk):
                # Dedupe key MUST match parser.py:116 — full sha256 of text.
                # Otherwise GraphQL posts and DOM posts can't dedupe each other.
                text = post.get("text") or ""
                if not text:
                    continue
                key = post_hash(text)
                if key in self._seen:
                    continue
                self._seen.add(key)
                self._posts.append(post)

    @staticmethod
    def _iter_json_chunks(body: bytes):
        """Facebook streams responses as either single JSON or NDJSON.
        Try whole-body first, then split on newlines.
        """
        try:
            text = body.decode("utf-8", errors="replace")
        except Exception:
            return
        text = text.strip()
        if not text:
            return
        try:
            yield json.loads(text)
            return
        except Exception:
            pass
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue

    @staticmethod
    def _walk_for_cursors(root):
        """Iterative DFS harvesting Facebook's pagination cursors.

        Cursors live in pageInfo objects:
            pageInfo.end_cursor         (older shape)
            pageInfo.endCursor          (camelCase)
            page_info.end_cursor         (snake-case container)
            cursor                       (edge-level)

        Yields cursor strings. Caller is responsible for deduping.
        """
        stack = [root]
        seen_obj_ids = set()
        while stack:
            node = stack.pop()
            if id(node) in seen_obj_ids:
                continue
            seen_obj_ids.add(id(node))
            if isinstance(node, dict):
                # Check both camelCase and snake_case page-info containers.
                for pi_key in ("pageInfo", "page_info"):
                    pi = node.get(pi_key)
                    if isinstance(pi, dict):
                        for ck in ("end_cursor", "endCursor", "after"):
                            v = pi.get(ck)
                            if isinstance(v, str) and len(v) > 4:
                                yield v
                # Edge-level cursor (some shapes)
                cur = node.get("cursor")
                if isinstance(cur, str) and len(cur) > 4:
                    yield cur
                for v in node.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(node, list):
                for item in node:
                    if isinstance(item, (dict, list)):
                        stack.append(item)

    @staticmethod
    def _walk_for_stories(root):
        """Iterative DFS over a GraphQL response tree, yielding post dicts.

        Facebook nests story payloads 30-60 levels deep. Recursion would risk
        Python's stack limit; explicit stack is safer.

        Two recognisers in priority order:

          1. **Comet post root** — any node with a `comet_sections` dict.
             FB's modern feed splits message and creation_time into
             *sibling subtrees* of `comet_sections` rather than placing them
             on the same node:
               comet_sections/content/story/message/text   (message)
               comet_sections/timestamp/story/creation_time (timestamp)
             A per-node check sees them as separate posts and misses
             timestamps. Path-based extraction across the comet_sections
             dict pulls the matching pair together.

          2. **Legacy per-node fallback** — older feed shapes where
             message.text and creation_time are on the same node.
             Kept for compatibility with non-Comet responses (mbasic, old
             FeedUnit envelopes).
        """
        from utils import post_hash, normalize_timestamp
        stack = [root]
        seen_ids = set()
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                # ── 1. Comet-style post root ─────────────────────────────
                cs = node.get("comet_sections")
                if isinstance(cs, dict):
                    post = _GraphQLPostExtractor._extract_comet_post(cs)
                    if post is not None:
                        h = post_hash(post["text"])
                        if h not in seen_ids:
                            seen_ids.add(h)
                            post["post_id"] = h[:16]
                            yield post
                    # Descend into siblings only — comet_sections' interior
                    # is fully handled by the path extractor above; walking
                    # into it would re-yield the same text via the legacy
                    # branch (with no timestamp) and waste cycles.
                    for k, v in node.items():
                        if k == "comet_sections":
                            continue
                        if isinstance(v, (dict, list)):
                            stack.append(v)
                    continue

                # ── 2. Legacy per-node fallback ──────────────────────────
                msg_text = _GraphQLPostExtractor._extract_message(node)
                if msg_text and len(msg_text) > 10:
                    h = post_hash(msg_text)
                    if h in seen_ids:
                        # already-yielded comet post — descend, don't yield
                        for v in node.values():
                            if isinstance(v, (dict, list)):
                                stack.append(v)
                        continue
                    seen_ids.add(h)
                    url = _GraphQLPostExtractor._extract_url(node)
                    ts_raw = _GraphQLPostExtractor._extract_creation_time(node)
                    ts_iso = None
                    if isinstance(ts_raw, (int, float)):
                        from datetime import datetime, timezone, timedelta
                        try:
                            ts_iso = datetime.fromtimestamp(
                                ts_raw, tz=timezone(timedelta(hours=8))
                            ).isoformat()
                        except Exception:
                            ts_iso = None
                    elif isinstance(ts_raw, str):
                        ts_iso = normalize_timestamp(ts_raw) or ts_raw
                    yield {
                        "text": msg_text,
                        "timestamp_iso": ts_iso,
                        "timestamp_raw": str(ts_raw) if ts_raw else None,
                        "engagement": _GraphQLPostExtractor._extract_engagement(node),
                        "post_url": url,
                        "post_id": h[:16],
                        "source": "graphql",
                    }
                # keep walking — a story can contain nested feed units
                for v in node.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(node, list):
                for item in node:
                    if isinstance(item, (dict, list)):
                        stack.append(item)

    @staticmethod
    def _extract_comet_post(cs: dict) -> Optional[dict]:
        """Extract a post from a Comet-style `comet_sections` dict.

        Returns a partial post dict (without post_id, which the caller
        attaches) or None if no message text is present.

        Known paths inside `comet_sections` (from probing live FB
        responses, May 2026):
          - content/story/message/text            -> post text
          - content/story/wwwURL or permalink_url -> post URL
          - timestamp/story/creation_time         -> unix timestamp (primary)
          - context_layout/story/comet_sections/metadata/[0]/story/creation_time
                                                  -> unix timestamp (fallback)
          - feedback/...                          -> engagement counts
        """
        from utils import normalize_timestamp

        # ---- message ----
        try:
            content_story = cs.get("content", {}).get("story", {})
        except AttributeError:
            return None
        if not isinstance(content_story, dict):
            return None
        msg = content_story.get("message")
        if not isinstance(msg, dict):
            return None
        msg_text = msg.get("text")
        if not isinstance(msg_text, str):
            return None
        msg_text = msg_text.strip()
        if not msg_text or len(msg_text) <= 10:
            return None

        # ---- creation_time ----
        ct_raw = None
        ts_node = cs.get("timestamp")
        if isinstance(ts_node, dict):
            story = ts_node.get("story")
            if isinstance(story, dict):
                ct_raw = story.get("creation_time")
        if ct_raw is None:
            try:
                metadata = (cs.get("context_layout", {})
                              .get("story", {})
                              .get("comet_sections", {})
                              .get("metadata", []))
                if isinstance(metadata, list):
                    for m in metadata:
                        if isinstance(m, dict):
                            s = m.get("story")
                            if isinstance(s, dict) and "creation_time" in s:
                                ct_raw = s["creation_time"]
                                break
            except Exception:
                pass

        ts_iso = None
        if isinstance(ct_raw, (int, float)):
            from datetime import datetime, timezone, timedelta
            try:
                ts_iso = datetime.fromtimestamp(
                    ct_raw, tz=timezone(timedelta(hours=8))
                ).isoformat()
            except Exception:
                ts_iso = None
        elif isinstance(ct_raw, str):
            ts_iso = normalize_timestamp(ct_raw) or ct_raw

        # ---- url ----
        url = None
        for k in ("wwwURL", "permalink_url", "url"):
            v = content_story.get(k)
            if isinstance(v, str) and "facebook.com" in v:
                url = v
                break

        # ---- engagement ----
        engagement = {"reactions": 0, "comments": 0, "shares": 0}
        fb_node = cs.get("feedback")
        if isinstance(fb_node, dict):
            engagement = _GraphQLPostExtractor._extract_engagement_comet(fb_node)

        return {
            "text": msg_text,
            "timestamp_iso": ts_iso,
            "timestamp_raw": str(ct_raw) if ct_raw is not None else None,
            "engagement": engagement,
            "post_url": url,
            "source": "graphql",
        }

    @staticmethod
    def _extract_message(node) -> Optional[str]:
        """Look for a message at THIS level only.

        DFS walks the whole tree, so we don't recurse here — that would cause
        URL / timestamp extraction to read from the wrong node level. The DFS
        will visit deeply nested story nodes naturally.
        """
        msg = node.get("message")
        if isinstance(msg, dict):
            t = msg.get("text")
            if isinstance(t, str):
                return t.strip() or None
        return None

    @staticmethod
    def _extract_url(node) -> Optional[str]:
        for key in ("wwwURL", "permalink_url", "url"):
            v = node.get(key)
            if isinstance(v, str) and "facebook.com" in v:
                return v
        return None

    @staticmethod
    def _extract_creation_time(node):
        v = node.get("creation_time")
        if v is not None:
            return v
        ts = node.get("timestamp") or node.get("created_time")
        return ts

    @staticmethod
    def _extract_engagement(node) -> dict:
        """Legacy engagement extractor (older feed shapes).

        Expects a node with a `feedback` child whose direct keys include
        reaction_count / comment_count / share_count. Kept for non-Comet
        responses. The Comet path uses _extract_engagement_comet which
        walks much deeper.
        """
        out = {"reactions": 0, "comments": 0, "shares": 0}
        try:
            fb = node.get("feedback") or {}
            if isinstance(fb, dict):
                rc = fb.get("reaction_count") or fb.get("reactors")
                if isinstance(rc, dict):
                    out["reactions"] = int(rc.get("count") or 0)
                cc = fb.get("comment_count") or fb.get("comments")
                if isinstance(cc, dict):
                    out["comments"] = int(cc.get("total_count") or cc.get("count") or 0)
                sc = fb.get("share_count")
                if isinstance(sc, dict):
                    out["shares"] = int(sc.get("count") or 0)
        except Exception:
            pass
        return out

    @staticmethod
    def _extract_engagement_comet(fb_root) -> dict:
        """Engagement extractor for Comet feedback subtrees.

        Comet nests reaction / comment / share counts ~8 levels deep
        inside `feedback`. We can't rely on a fixed path because FB
        shifts the structure between query variants. Instead, walk the
        whole subtree and harvest:

          - `reaction_count`/`i18n_reaction_count` dicts → extract `count`
            (the *aggregate* total across all emojis). Skip per-edge
            entries which are int-typed (top_reactions/edges/[N]/reaction_count).
          - `share_count` dict → extract `count`.
          - `comment_rendering_instance.comments.total_count` → comments.

        Returns the maximum count seen for each metric (FB sometimes
        renders the same number in multiple places — taking max is
        defensive against partial structures).
        """
        out = {"reactions": 0, "comments": 0, "shares": 0}
        if not isinstance(fb_root, dict):
            return out
        stack = [fb_root]
        seen = set()
        while stack:
            node = stack.pop()
            nid = id(node)
            if nid in seen:
                continue
            seen.add(nid)
            if isinstance(node, dict):
                # Aggregate reaction_count: dict shape {count: int, ...}.
                rc = node.get("reaction_count")
                if isinstance(rc, dict):
                    n = rc.get("count")
                    if isinstance(n, (int, float)):
                        out["reactions"] = max(out["reactions"], int(n))
                # i18n_reaction_count is sometimes the canonical form.
                irc = node.get("i18n_reaction_count")
                if isinstance(irc, str):
                    try:
                        out["reactions"] = max(out["reactions"], int(irc))
                    except ValueError:
                        pass
                # share_count: dict shape {count: int}.
                sc = node.get("share_count")
                if isinstance(sc, dict):
                    n = sc.get("count")
                    if isinstance(n, (int, float)):
                        out["shares"] = max(out["shares"], int(n))
                # comment_rendering_instance.comments.total_count.
                cri = node.get("comment_rendering_instance")
                if isinstance(cri, dict):
                    cms = cri.get("comments")
                    if isinstance(cms, dict):
                        n = cms.get("total_count")
                        if isinstance(n, (int, float)):
                            out["comments"] = max(out["comments"], int(n))
                # Recurse.
                for v in node.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(node, list):
                for v in node:
                    if isinstance(v, (dict, list)):
                        stack.append(v)
        return out


class _SessionRestarter:
    """Save/restore a scraper session across browser restarts.

    Persists cookies + localStorage + last permalink + scroll counter to disk,
    closes the current browser/context, launches a fresh one with the same
    anti-detection flags, restores state after navigation, and fast-forwards
    the scroll until the last seen permalink is in view (or a time cap fires).

    Holds a back-reference to the FacebookScraper to reuse its launch helper.
    """

    def __init__(self, scraper):
        self._scraper = scraper
        self.cycles = 0
        self._watchdog = None  # set by main loop so fast-forward can heartbeat

    def save(self, page, context, code: str, last_permalink: Optional[str],
             scroll_n: int, post_count: int,
             seen_cursors: Optional[set] = None) -> None:
        try:
            cookies = context.cookies()
        except Exception:
            cookies = []
        try:
            ls = page.evaluate(
                "() => { const o = {}; for (let i=0;i<localStorage.length;i++){"
                "const k = localStorage.key(i); o[k] = localStorage.getItem(k);} return o; }"
            ) or {}
        except Exception:
            ls = {}
        # Cap saved cursors to keep state file small; recent ones are most useful.
        cursor_list = list(seen_cursors) if seen_cursors else []
        if len(cursor_list) > 5000:
            cursor_list = cursor_list[-5000:]
        state = {
            "cookies": cookies,
            "localStorage": ls,
            "last_permalink": last_permalink,
            "scroll_count": scroll_n,
            "post_count": post_count,
            "seen_cursors": cursor_list,
            "ts": time.time(),
        }
        path = os.path.join(self._scraper.cfg.output_dir, f"{code}_session.json")
        try:
            os.makedirs(self._scraper.cfg.output_dir, exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)
            os.replace(tmp, path)
            logger.info(
                "[%s] Session state saved: %d cookies, %d ls keys, %d cursors, scroll=%d, posts=%d",
                code, len(cookies), len(ls), len(cursor_list), scroll_n, post_count,
            )
        except Exception as exc:
            logger.warning("[%s] Could not save session state: %s", code, exc)

    def cycle(self, pw, browser, context, page, code: str, target_url: str,
              extractor, scroll_n: int, posts: list) -> tuple:
        """Run one full restart: save -> close -> relaunch -> restore -> fast-forward.

        Returns (browser, context, page) for the resumed session. The fast-forward
        is now CURSOR-DRIVEN: scroll aggressively until the extractor yields a
        cursor NOT already in seen_cursors. That signals Facebook is serving
        content past where we left off — at which point dedupe overlap is
        minimal and the regular scroll loop takes over.
        """
        last_permalink = None
        for p in reversed(posts):
            if p.get("post_url"):
                last_permalink = p["post_url"]
                break
        self.save(
            page, context, code, last_permalink, scroll_n, len(posts),
            seen_cursors=extractor._cursors if extractor else None,
        )

        try:
            context.close()
        except Exception:
            pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

        # Brief pause: gives Windows time to release the persistent profile lock.
        time.sleep(2.0)
        self.cycles += 1
        logger.info("[%s] Restart cycle #%d — relaunching browser", code, self.cycles)

        browser, context = self._scraper._launch_desktop_session(pw, code)
        if self._scraper.cfg.block_media:
            try:
                context.route(
                    "**/*.{png,jpg,jpeg,gif,svg,mp4,webm,webp,ico,woff,woff2}",
                    lambda route: route.abort(),
                )
            except Exception:
                pass
        page = context.new_page()
        page.add_init_script(NAV_WEBDRIVER_OVERRIDE)

        try:
            page.goto(
                target_url,
                timeout=self._scraper.cfg.page_load_timeout,
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(2500)
        except Exception as exc:
            logger.warning("[%s] goto after restart failed: %s", code, exc)

        # Restore localStorage AFTER goto (domain-scoped).
        self._scraper._restore_session_state(page)

        # Re-attach extractor on the new page BEFORE fast-forward so we can
        # detect new content via network responses. Reset the per-session
        # cursor list so fast-forward's freshness baseline is clean.
        if extractor is not None:
            extractor.cursors_seen_this_session = []
        if self._scraper.cfg.network_intercept_mode:
            extractor.attach(page)

        self.fast_forward_via_extractor(page, extractor, code, watchdog=self._watchdog)

        return browser, context, page

    def fast_forward_via_extractor(self, page, extractor, code: str,
                                   max_scrolls: int = 2000,
                                   max_seconds: int = 600,
                                   target_fresh_posts: int = 15,
                                   watchdog=None) -> bool:
        """Yield-driven fast-forward.

        Scrolls aggressively (no random delay) and watches how many GENUINELY
        new posts the extractor accumulates — i.e. posts whose content-hash
        is not already in the shared dedupe set. When we've accumulated
        target_fresh_posts unseen posts, we've crossed the boundary cleanly
        and the main loop can take over with minimal duplicate slog.

        Why post-yield instead of cursor-uniqueness: Facebook issues fresh
        cursor tokens on every request even when the underlying content is
        the same. Cursor newness does NOT imply content newness; only the
        post-hash dedupe set tells the truth.

        The accumulated posts are NOT drained during fast-forward — they
        stay in extractor._posts so the main loop's first drain() picks
        them up immediately, no posts lost.
        """
        if extractor is None:
            return False
        baseline_fresh = len(extractor._posts)
        deadline = time.monotonic() + max_seconds
        ff_start = time.monotonic()
        last_log_t = ff_start

        for i in range(max_scrolls):
            if time.monotonic() > deadline:
                break

            # Reset the watchdog heartbeat so a long fast-forward doesn't
            # get killed as if the page were frozen.
            if watchdog is not None:
                watchdog.heartbeat()

            fresh_now = len(extractor._posts) - baseline_fresh
            if fresh_now >= target_fresh_posts:
                elapsed = time.monotonic() - ff_start
                logger.info(
                    "[%s] Fast-forward: yielded %d fresh posts at scroll %d in %.1fs — boundary crossed",
                    code, fresh_now, i, elapsed,
                )
                return True

            try:
                # Use the same scrollBy pattern as the regular loop — it's
                # proven to trigger Facebook's lazy-load reliably. 1500px is
                # within the rendered viewport so scroll events actually fire.
                page.evaluate("window.scrollBy(0, 1500)")
                page.wait_for_timeout(700)
            except Exception:
                break

            if time.monotonic() - last_log_t > 20:
                last_log_t = time.monotonic()
                logger.info(
                    "[%s] Fast-forward in progress: scroll=%d/%d, responses=%d, fresh_posts=%d/%d",
                    code, i, max_scrolls, extractor.responses_seen,
                    fresh_now, target_fresh_posts,
                )

        elapsed = time.monotonic() - ff_start
        fresh_total = len(extractor._posts) - baseline_fresh
        logger.warning(
            "[%s] Fast-forward: only %d fresh posts in %d scrolls / %.0fs — falling through; main loop continues",
            code, fresh_total, max_scrolls, elapsed,
        )
        return False


class FacebookScraper:
    """Orchestrates scraping of a single Facebook page."""

    def __init__(self, config: ScraperConfig):
        self.cfg = config
        self._cookies: list[dict] = []
        self._session_state: dict = {}   # localStorage saved by extract_cookies.py
        self._cdp_sessions: dict = {}    # cache CDP sessions per-page id
        # Per-target sets of post_id strings already appended to {code}.jsonl —
        # prevents the same post from being re-appended on every 30s checkpoint.
        self._jsonl_written_ids: dict[str, set[str]] = {}
        if config.cookie_file and os.path.exists(config.cookie_file):
            self._load_cookies(config.cookie_file)

    def _load_cookies(self, path: str) -> None:
        """Load Facebook session cookies (and localStorage state) from extract_cookies.py output."""
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self._cookies = [
            c for c in raw
            if "facebook.com" in c.get("domain", "")
        ]

        # Also load the companion localStorage state file if present.
        # extract_cookies.py saves this alongside cookies.json as cookies_state.json.
        # Without localStorage, a cookie-only session stalls after ~80-100 posts
        # because Facebook's infinite-scroll API relies on tokens stored there.
        state_path = os.path.splitext(path)[0] + "_state.json"
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    self._session_state = json.load(f)
                ls_count = len(self._session_state.get("localStorage", {}))
                logger.info("Loaded session state (%d localStorage keys) from %s", ls_count, state_path)
            except Exception as _e:
                logger.warning("Could not load session state from %s: %s", state_path, _e)

        if self._cookies:
            self.cfg.authenticated = True
            self.cfg.page_timeout_seconds = 28800      # 8-hour production run
            self.cfg.max_scroll_attempts = 5000
            self.cfg.stale_scroll_limit = 30
            self.cfg.scroll_delay_min = 1.5
            self.cfg.scroll_delay_max = 3.5
            logger.info(
                "Loaded %d cookies -- authenticated mode ON "
                "(timeout=%ds, max_scrolls=%d, delay=%.1f-%.1fs)",
                len(self._cookies),
                self.cfg.page_timeout_seconds,
                self.cfg.max_scroll_attempts,
                self.cfg.scroll_delay_min,
                self.cfg.scroll_delay_max,
            )

    def _restore_session_state(self, page: Page) -> None:
        """Inject saved localStorage into the current page.

        Must be called AFTER page.goto() — localStorage is domain-scoped
        and cannot be set before the browser is on the target domain.
        Silently skips if no session state was loaded.
        """
        ls = (self._session_state or {}).get("localStorage", {})
        if not ls:
            return
        try:
            page.evaluate("""(state) => {
                try {
                    Object.entries(state).forEach(([k, v]) => {
                        try { localStorage.setItem(k, v); } catch(e) {}
                    });
                } catch(e) {}
            }""", ls)
            logger.info("Restored %d localStorage keys into session", len(ls))
        except Exception as _e:
            logger.warning("Could not restore localStorage: %s", _e)

    def _safe_evaluate(self, page: Page, script: str, arg=None, timeout_secs: int = 30):
        """Thin wrapper around page.evaluate().

        The ScrollWatchdog handles stall timeouts (90 s ctypes injection).
        This wrapper provides a uniform call signature so shared helpers work
        in both the main scraper and any test worktrees.

        Note: Playwright's Python page.evaluate() does not accept a timeout
        parameter — per-call timeouts are not supported by the binding.
        The ScrollWatchdog is the timeout mechanism for stuck evaluate() calls.
        """
        if arg is not None:
            return page.evaluate(script, arg)
        return page.evaluate(script)

    def _cdp_gc(self, context, page) -> None:
        """Force V8 garbage collection via Chrome DevTools Protocol.

        innerHTML='' alone cannot reclaim heap that V8 has fragmented. A direct
        HeapProfiler.collectGarbage call performs a major GC pass and tends to
        return ~30-50% of "leaked" heap to the OS. Cached per-page CDP session
        because a new session takes ~150 ms.
        """
        try:
            sess = self._cdp_sessions.get(id(page))
            if sess is None:
                sess = context.new_cdp_session(page)
                self._cdp_sessions[id(page)] = sess
            sess.send("HeapProfiler.collectGarbage")
        except Exception as exc:
            logger.debug("CDP GC failed: %s", exc)

    def _log_heap(self, page, code: str, scroll_n: int,
                  extractor: Optional[_GraphQLPostExtractor],
                  posts_count: int) -> None:
        """Periodic heap + extractor stats line. Cheap; runs every 50 scrolls."""
        try:
            mem = page.evaluate(
                "() => performance && performance.memory ? "
                "{ used: performance.memory.usedJSHeapSize, "
                "  total: performance.memory.totalJSHeapSize } : null"
            )
        except Exception:
            mem = None
        used_mb = round(mem["used"] / (1024 * 1024), 1) if mem else "n/a"
        total_mb = round(mem["total"] / (1024 * 1024), 1) if mem else "n/a"
        if extractor:
            bytes_mb = round(extractor.bytes_seen / (1024 * 1024), 2)
            logger.info(
                "[%s] scroll=%d heap_used=%smb total=%smb graphql_resp=%d bytes=%smb posts=%d",
                code, scroll_n, used_mb, total_mb,
                extractor.responses_seen, bytes_mb, posts_count,
            )
        else:
            logger.info(
                "[%s] scroll=%d heap_used=%smb total=%smb posts=%d",
                code, scroll_n, used_mb, total_mb, posts_count,
            )

    def _launch_desktop_session(self, pw, code: str):
        """Launch (browser, context) using the proven 3-tier fallback chain.

        Used both at initial startup and on every session restart. Returns
        (browser, context) — browser is None when launched via persistent
        context (Playwright manages it internally in that mode).
        """
        import tempfile
        import shutil

        if not self.cfg.persistent_profile_dir:
            self.cfg.persistent_profile_dir = os.path.join(
                tempfile.gettempdir(), "fb_login_profile"
            )

        # Remove stale lock files left by previously force-killed Chrome instances.
        for _lock in ("SingletonLock", "SingletonSocket", "SingletonCookie", "lockfile"):
            _lp = os.path.join(self.cfg.persistent_profile_dir, _lock)
            try:
                os.remove(_lp)
            except FileNotFoundError:
                pass
            except Exception:
                pass

        common_args = self._desktop_chrome_args(
            extra=["--disable-translate", "--disable-default-apps"]
        )
        viewport = {"width": self.cfg.viewport_width, "height": self.cfg.viewport_height}

        if self.cfg.use_persistent_context:
            try:
                context = pw.chromium.launch_persistent_context(
                    self.cfg.persistent_profile_dir,
                    headless=self.cfg.headless,
                    channel=self.cfg.browser_channel,
                    args=common_args,
                    ignore_default_args=["--enable-automation"],
                    viewport=viewport,
                    user_agent=self.cfg.user_agent,
                    locale="en-US",
                    **self._headed_launch_kwargs(),
                )
                logger.info("[%s][desktop] Persistent context launched", code)
                return None, context
            except Exception as _err1:
                logger.warning(
                    "[%s] Persistent context failed (%s) -- profile corrupted, deleting and retrying",
                    code, type(_err1).__name__,
                )
                try:
                    shutil.rmtree(self.cfg.persistent_profile_dir, ignore_errors=True)
                    os.makedirs(self.cfg.persistent_profile_dir, exist_ok=True)
                except Exception as _del_err:
                    logger.warning("[%s] Could not delete profile: %s", code, _del_err)

                try:
                    context = pw.chromium.launch_persistent_context(
                        self.cfg.persistent_profile_dir,
                        headless=self.cfg.headless,
                        channel=self.cfg.browser_channel,
                        args=common_args,
                        ignore_default_args=["--enable-automation"],
                        viewport=viewport,
                        user_agent=self.cfg.user_agent,
                        locale="en-US",
                        **self._headed_launch_kwargs(),
                    )
                    if self._cookies:
                        context.add_cookies(self._cookies)
                        logger.info(
                            "[%s][desktop] Fresh persistent context -- injected %d cookies",
                            code, len(self._cookies),
                        )
                    return None, context
                except Exception:
                    logger.warning(
                        "[%s] Fresh persistent context also failed -- falling back to browser.new_context()", code
                    )

        # Final fallback: regular browser.new_context()
        browser = pw.chromium.launch(
            headless=self.cfg.headless,
            channel=self.cfg.browser_channel,
            args=common_args,
            ignore_default_args=["--enable-automation"],
            **self._headed_launch_kwargs(),
        )
        context = browser.new_context(
            viewport=viewport,
            user_agent=self.cfg.user_agent,
            locale="en-US",
        )
        if self._cookies:
            context.add_cookies(self._cookies)
            logger.info(
                "[%s][desktop] Injected %d cookies (fallback context)",
                code, len(self._cookies),
            )
        return browser, context

    def _desktop_chrome_args(self, extra: Optional[list] = None) -> list:
        """Build Chrome launch args for the desktop strategy.

        Anti-detection flags and configurable V8 heap size are always included.
        --start-maximized is appended only when self.cfg.headed is True so the
        debug window opens full-screen for visual diagnosis of the freeze.
        """
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-notifications",
        ]
        if extra:
            args.extend(extra)
        args.append(f"--js-flags=--max_old_space_size={self.cfg.js_heap_size_mb}")
        if self.cfg.headed:
            args.append("--start-maximized")
        return args

    def _headed_launch_kwargs(self) -> dict:
        """slow_mo=50 only when headed=True (visual debug); empty otherwise."""
        return {"slow_mo": 50} if self.cfg.headed else {}

    class _ScrollWatchdog:
        """Watchdog that injects KeyboardInterrupt into the main thread if a
        single scroll iteration takes longer than timeout_secs.

        WHY NOT threading.Thread + page.evaluate():
        Playwright's sync API uses greenlets internally — page.evaluate() MUST
        be called from the same thread/greenlet that owns the Playwright context.
        Calling it from a Thread causes "cannot switch to a different thread".

        Instead, the watchdog thread does NOT call any Playwright functions.
        It only calls ctypes.PyThreadState_SetAsyncExc, which safely injects a
        KeyboardInterrupt into the main thread at the next Python bytecode
        boundary. Playwright's asyncio event loop returns to Python within ~1 s
        (after each selector.select() timeout), so the interrupt lands quickly.
        """

        def __init__(self, timeout_secs: int = 90):
            self._timeout = timeout_secs
            self._last_beat = time.monotonic()
            self._stopped = threading.Event()
            self._main_tid = threading.main_thread().ident
            self._t = threading.Thread(target=self._run, daemon=True)
            self._t.start()

        def heartbeat(self) -> None:
            """Call at the start of each scroll iteration to reset the timer."""
            self._last_beat = time.monotonic()

        def stop(self) -> None:
            self._stopped.set()

        def _run(self) -> None:
            while not self._stopped.wait(timeout=5):
                if time.monotonic() - self._last_beat > self._timeout:
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(
                        ctypes.c_long(self._main_tid),
                        ctypes.py_object(KeyboardInterrupt),
                    )
                    break

    # ── Public API ───────────────────────────────────────────────────────────

    def scrape_target(self, target: dict) -> dict:
        code = target["code"]
        url = target["url"]
        logger.info("=" * 60)
        logger.info("Starting scrape for %s", code)

        best_posts: list[dict] = []
        strategy_used = "none"
        status = "no_data"
        start = time.monotonic()

        for strategy in self.cfg.strategies:
            logger.info("[%s] Trying strategy: %s", code, strategy)
            try:
                posts = self._run_strategy(strategy, url, code)
                logger.info("[%s] Strategy '%s' yielded %d posts", code, strategy, len(posts))
                if len(posts) > len(best_posts):
                    best_posts = posts
                    strategy_used = strategy
                if len(best_posts) >= self.cfg.target_posts:
                    status = "target_reached"
                    break
                if len(best_posts) >= self.cfg.min_posts_threshold:
                    status = "partial_collected"
            except Exception as exc:
                logger.error("[%s] Strategy '%s' failed: %s", code, strategy, exc)
                continue

        best_posts = deduplicate_posts(best_posts)
        elapsed = time.monotonic() - start

        if not best_posts:
            status = "no_data"
        elif len(best_posts) >= self.cfg.target_posts:
            status = "target_reached"
        elif status != "partial_collected":
            status = "partial_login_wall"

        logger.info(
            "[%s] Final: %d posts via '%s' in %.0fs — status: %s",
            code, len(best_posts), strategy_used, elapsed, status,
        )

        return {
            "metadata": {
                "institution_code": code,
                "strategy_used": strategy_used,
                "total_posts_collected": len(best_posts),
                "target_posts": self.cfg.target_posts,
                "collection_status": status,
                "duration_seconds": round(elapsed, 1),
                "scraper_version": self.cfg.scraper_version,
            },
            "posts": best_posts,
        }

    # ── Strategy router ──────────────────────────────────────────────────────

    def _run_strategy(self, strategy: str, url: str, code: str) -> list[dict]:
        if strategy == "desktop_graphql_httpx":
            return self._desktop_graphql_httpx_strategy(url, code)
        if strategy == "desktop":
            return self._desktop_strategy(url, code)
        if strategy == "basic_mobile_httpx":
            return self._basic_mobile_strategy_httpx(url, code)
        if strategy == "basic_mobile":
            return self._basic_mobile_strategy(url, code)
        logger.warning("Unknown strategy: %s", strategy)
        return []

    # ── Strategy 0: Desktop GraphQL replay (ACTION-032) ─────────────────────
    # Bypasses the V8/Chrome-RSS freeze cliff by harvesting one pagination
    # request via a brief Playwright session, then replaying /api/graphql/
    # POSTs through the same browser's APIRequestContext. The browser
    # remains open as a thin HTTP client (no further DOM rendering, no
    # scrolling), so RSS stays bounded at ~100 MB regardless of post count.
    # Falls through to the desktop Playwright strategy on harvest failure.

    def _desktop_graphql_httpx_strategy(self, url: str, code: str) -> list[dict]:
        import graphql_httpx

        # Resume from any existing checkpoint — same JSONL contract as the
        # desktop strategy, so a partial run via either strategy can be
        # continued by the other.
        posts: list[dict] = []
        seen_hashes: set[str] = set()
        try:
            for _p in self._checkpoint_load(code):
                _t = _p.get("text") or ""
                if not _t:
                    continue
                _h = post_hash(_t)
                if _h in seen_hashes:
                    continue
                seen_hashes.add(_h)
                _pid = _p.get("post_id") or _h[:16]
                _p["post_id"] = _pid
                self._jsonl_written_ids.setdefault(code, set()).add(_pid)
                posts.append(_p)
            if posts:
                logger.info(
                    "[%s][graphql_httpx] Resumed checkpoint: %d posts pre-loaded",
                    code, len(posts),
                )
        except Exception as exc:
            logger.warning("[%s][graphql_httpx] Resume failed: %s", code, exc)

        if not self._cookies:
            logger.warning(
                "[%s][graphql_httpx] No cookies loaded — graphql replay "
                "requires authenticated session; falling through",
                code,
            )
            return posts

        consecutive_harvest_failures = 0
        tokens = None
        # Track the latest cursor across refreshes so we resume where we
        # left off instead of fast-forwarding through every previously-
        # collected post (which on a 4000-post run would consume the
        # entire next session). On the first call we pass start_cursor=None
        # and paginate uses the cursor captured during harvest.
        last_cursor: Optional[str] = None
        try:
            while True:
                # (Re)harvest tokens.
                if tokens is None or graphql_httpx.should_refresh(tokens, self.cfg):
                    if tokens is not None:
                        graphql_httpx.close_session(tokens)
                        tokens = None
                    logger.info("[%s][graphql_httpx] harvesting tokens...", code)
                    tokens = graphql_httpx.harvest_tokens(
                        self, self.cfg, code, url, logger=logger,
                    )
                    if tokens is None:
                        consecutive_harvest_failures += 1
                        logger.warning(
                            "[%s][graphql_httpx] harvest failed "
                            "(%d/%d) — falling through to next strategy",
                            code, consecutive_harvest_failures,
                            self.cfg.max_retries,
                        )
                        if consecutive_harvest_failures >= self.cfg.max_retries:
                            return posts
                        # Brief backoff, then retry.
                        time.sleep(self.cfg.retry_backoff_base
                                   * (2 ** consecutive_harvest_failures))
                        continue
                    consecutive_harvest_failures = 0

                # Drive the pagination loop until target / end-of-feed /
                # token expiry / errors. Threads last_cursor across refreshes.
                posts, stop_reason, last_cursor = graphql_httpx.paginate(
                    self, self.cfg, code, tokens, posts, seen_hashes,
                    start_cursor=last_cursor,
                    logger=logger,
                )
                logger.info(
                    "[%s][graphql_httpx] paginate exited: %s "
                    "(posts=%d/%d)",
                    code, stop_reason, len(posts), self.cfg.target_posts,
                )

                if stop_reason in ("target_reached", "end_of_feed"):
                    break
                if stop_reason == "rate_limited":
                    # Facebook rate limit — re-harvesting would make it worse
                    # (more graphql requests against an already-over-limit
                    # account). Stop cleanly. The user will wait it out and
                    # rerun the same command later; JSONL is preserved so the
                    # resume picks up from here.
                    logger.error(
                        "[%s][graphql_httpx] rate-limited by Facebook — "
                        "stopping. Wait at least 1 hour before retrying. "
                        "JSONL preserved (%d posts collected).",
                        code, len(posts),
                    )
                    break
                if stop_reason == "token_expired":
                    # Loop around to re-harvest fresh tokens.
                    graphql_httpx.close_session(tokens)
                    tokens = None
                    continue
                if stop_reason in ("max_errors", "max_iterations", "killed"):
                    logger.warning(
                        "[%s][graphql_httpx] terminal stop_reason=%s — "
                        "falling through with %d posts collected",
                        code, stop_reason, len(posts),
                    )
                    break

            # Final flush — paginate() checkpoints during the loop, but a
            # clean exit on target/end-of-feed deserves a guaranteed flush.
            try:
                self._checkpoint_save(posts, code)
            except Exception as exc:
                logger.warning("[%s][graphql_httpx] final checkpoint: %s",
                               code, exc)
            return posts
        except KeyboardInterrupt:
            logger.warning("[%s][graphql_httpx] interrupted — flushing %d posts",
                           code, len(posts))
            try:
                self._checkpoint_save(posts, code)
            except Exception:
                pass
            raise
        finally:
            graphql_httpx.close_session(tokens)

    # ── Strategy 1: Desktop ──────────────────────────────────────────────────

    def _desktop_strategy(self, url: str, code: str) -> list[dict]:
        posts: list[dict] = []
        seen_hashes: set[str] = set()
        last_error = None

        for attempt in range(self.cfg.max_retries):
            try:
                posts, seen_hashes = self._desktop_run(url, code)
                return posts
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                last_error = exc
                wait = self.cfg.retry_backoff_base * (2 ** attempt) + random.uniform(0, 2)
                logger.warning(
                    "[%s][desktop] Attempt %d failed: %s — retrying in %.1fs",
                    code, attempt + 1, exc, wait,
                )
                time.sleep(wait)

        if last_error:
            logger.error("[%s][desktop] All retries exhausted: %s", code, last_error)
        return posts

    def _desktop_run(self, url: str, code: str) -> tuple[list[dict], set[str]]:
        """Freeze-proof desktop scraping run.

        Architecture:
          - Network interception (always on, gated by cfg.network_intercept_mode):
            _GraphQLPostExtractor passively captures Facebook's /api/graphql/
            POST responses and parses out post nodes. Immune to DOM-size freezes.
          - DOM extraction (graceful fallback): activates when interception has
            been dry for >3 consecutive scrolls. Reuses the existing markPosts +
            outerHTML + _cleanup_dom path verbatim.
          - Periodic browser restart: every cfg.max_scrolls_per_session scrolls
            (default 150), close + relaunch context with full state resume. This
            purges accumulated V8 heap, CDP buffers, React reconciliation state.
          - CDP forced GC: every cfg.memory_check_interval scrolls (default 50),
            send HeapProfiler.collectGarbage. Reclaims fragmented heap that
            innerHTML='' alone cannot.
          - Pre-freeze diagnostic: if a single scroll dwells >30 s without new
            posts, snap a screenshot to debug_screenshots/ before continuing.

        Existing safety mechanisms preserved: _ScrollWatchdog (90 s ctypes
        injection), all anti-detection flags, localStorage restore-after-goto.
        """
        posts: list[dict] = []
        seen_hashes: set[str] = set()
        self._cdp_sessions = {}
        restarter = _SessionRestarter(self)
        sessions_without_progress = 0

        # Resume from a prior checkpoint if one exists. The corresponding
        # session_state file (loaded later inside the playwright block) carries
        # the cursor set so the cursor-driven fast-forward can skip the
        # duplicate prefix on first session.
        try:
            _prev_posts = self._checkpoint_load(code)
        except Exception as _exc:
            logger.warning("[%s] Could not resume checkpoint: %s", code, _exc)
            _prev_posts = []
        if _prev_posts:
            _written = self._jsonl_written_ids.setdefault(code, set())
            for _p in _prev_posts:
                _t = _p.get("text") or ""
                if not _t:
                    continue
                _h = post_hash(_t)
                if _h in seen_hashes:
                    continue
                seen_hashes.add(_h)
                _pid = _p.get("post_id") or _h[:16]
                _p["post_id"] = _pid
                _written.add(_pid)
                posts.append(_p)
            if posts:
                logger.info(
                    "[%s] Resumed from checkpoint: %d posts pre-loaded into dedupe set",
                    code, len(posts),
                )

        with sync_playwright() as pw:
            browser, context = self._launch_desktop_session(pw, code)

            if self.cfg.block_media:
                try:
                    context.route(
                        "**/*.{png,jpg,jpeg,gif,svg,mp4,webm,webp,ico,woff,woff2}",
                        lambda route: route.abort(),
                    )
                except Exception:
                    pass

            page: Page = context.new_page()
            page.add_init_script(NAV_WEBDRIVER_OVERRIDE)

            try:
                logger.info("[%s][desktop] Navigating to %s", code, url)
                page.goto(url, timeout=self.cfg.page_load_timeout, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                self._restore_session_state(page)

                # Detect login redirect (cookies expired etc.)
                current_url = page.url
                if any(kw in current_url for kw in ("login", "checkpoint", "recover", "disabled")):
                    logger.error(
                        "[%s] Facebook redirected to auth page (%s) -- cookies may be expired.",
                        code, current_url,
                    )
                    tqdm.write(
                        f"[{code}] ERROR: Facebook redirected to login. Re-run extract_cookies.py."
                    )
                    return posts, seen_hashes

                self._dismiss_overlays(page, code)
                self._dismiss_chat_popups(page, code)
                page.wait_for_timeout(2000)
                self._navigate_to_posts_tab(page, code)
                self._dismiss_chat_popups(page, code)  # navigate may re-open chat tabs

                stale_count = 0
                # unique_stale_count tracks scrolls since seen_hashes last grew.
                # Unlike stale_count (suppressed when network_alive), this fires
                # even when GraphQL keeps returning duplicates — which is the
                # signature of either dedup-saturation post-restart, end-of-feed,
                # or an approaching freeze.
                unique_stale_count = 0
                last_unique_count = len(seen_hashes)
                modal_dismiss_count = 0
                _last_checkpoint_t = time.monotonic()
                deadline = time.monotonic() + self.cfg.page_timeout_seconds

                pbar = tqdm(
                    total=self.cfg.target_posts,
                    desc=f"[{code}]",
                    unit="post",
                    dynamic_ncols=True,
                )
                pbar.set_postfix(scroll=0, stale=0, sess=1)

                watchdog = self._ScrollWatchdog(timeout_secs=90)
                restarter._watchdog = watchdog  # share with fast-forward to keep heartbeat alive

                # Attach the always-on GraphQL extractor. Pre-seed it with any
                # cursors saved from a previous run so a freshly-restarted run
                # doesn't have to re-discover the entire dedupe prefix.
                preloaded_cursors: set[str] = set()
                _state_path = os.path.join(self.cfg.output_dir, f"{code}_session.json")
                if os.path.exists(_state_path):
                    try:
                        with open(_state_path, "r", encoding="utf-8") as _sf:
                            _prev = json.load(_sf)
                        for c in _prev.get("seen_cursors") or []:
                            if isinstance(c, str):
                                preloaded_cursors.add(c)
                        logger.info(
                            "[%s] Pre-loaded %d cursors from prior session state",
                            code, len(preloaded_cursors),
                        )
                    except Exception as _exc:
                        logger.warning("[%s] Could not read prior session state: %s", code, _exc)

                extractor = _GraphQLPostExtractor(seen_hashes, seen_cursors=preloaded_cursors)
                if self.cfg.network_intercept_mode:
                    extractor.attach(page)
                    logger.info("[%s] GraphQL interception attached", code)

                # If we resumed from a checkpoint with posts already pre-loaded,
                # the page is freshly at the top of the feed — Facebook will
                # serve us a long prefix of duplicates before reaching unseen
                # content. Run the same yield-driven fast-forward used after
                # restart cycles so we don't waste hundreds of scrolls on
                # already-deduplicated content.
                if posts:
                    logger.info(
                        "[%s] Resume mode: %d posts pre-loaded; the regular loop "
                        "will dedupe-skip the prefix until new content arrives. "
                        "Resume-mode fast-forward is disabled because Facebook's "
                        "warm persistent profile serves cached content without "
                        "firing graphql until real user activity occurs.",
                        code, len(posts),
                    )

                total_scrolls = 0
                stop_outer = False
                stop_reason = ""
                # Time-based network_alive: track when responses_seen last
                # changed. Any response within network_alive_window_secs
                # counts the page as alive. Robust against bursty/asymmetric
                # response timing relative to scroll iterations.
                prev_responses_seen = (
                    extractor.responses_seen if self.cfg.network_intercept_mode else 0
                )
                last_response_seen_t = time.monotonic()
                # Heap-pressure early restart trigger.
                heap_pressure_triggered = False

                try:
                    while not stop_outer:
                        # ── Per-session loop ──────────────────────────────────
                        consecutive_dry = 0
                        scroll_in_session = 0
                        last_progress_scroll = total_scrolls
                        session_start_post_count = len(posts)
                        last_scroll_progress_t = time.monotonic()
                        prefreeze_screenshot_taken = False
                        heap_pressure_triggered = False

                        while scroll_in_session < self.cfg.max_scrolls_per_session:
                            watchdog.heartbeat()
                            total_scrolls += 1
                            scroll_in_session += 1

                            if time.monotonic() > deadline:
                                tqdm.write(f"[{code}][desktop] Timeout after {total_scrolls} scrolls")
                                stop_outer = True
                                stop_reason = "page_timeout"
                                break

                            if total_scrolls >= self.cfg.max_scroll_attempts:
                                tqdm.write(
                                    f"[{code}][desktop] Hit max_scroll_attempts={self.cfg.max_scroll_attempts}"
                                )
                                stop_outer = True
                                stop_reason = "max_scrolls"
                                break

                            # Dismiss overlays — same cadence as before.
                            if total_scrolls == 4 or (
                                not self.cfg.authenticated
                                and total_scrolls > 0
                                and total_scrolls % 30 == 0
                            ):
                                self._dismiss_overlays(page, code)

                            # Dismiss Messenger chat popups + comment-thread
                            # dialogs every 20 scrolls. These appear randomly
                            # during long auth-mode runs and absorb scroll
                            # events, causing the feed to stall even though
                            # graphql keeps firing for chat traffic.
                            if total_scrolls > 0 and total_scrolls % 20 == 0:
                                self._dismiss_chat_popups(page, code)

                            # ── 1. Drain the network extractor (always-on) ────
                            # Time-based network_alive: any response within
                            # network_alive_window_secs counts as alive. This
                            # is robust against bursty timing — responses
                            # arrive async, sometimes mid-iteration, sometimes
                            # during sleep, sometimes batched.
                            new_count_net = 0
                            current_responses_seen = (
                                extractor.responses_seen if self.cfg.network_intercept_mode else 0
                            )
                            if current_responses_seen > prev_responses_seen:
                                last_response_seen_t = time.monotonic()
                                prev_responses_seen = current_responses_seen
                            network_alive = (
                                self.cfg.network_intercept_mode
                                and (time.monotonic() - last_response_seen_t)
                                    < self.cfg.network_alive_window_secs
                            )
                            if self.cfg.network_intercept_mode:
                                drained = extractor.drain()
                                for parsed in drained:
                                    if self._is_comment_or_noise(parsed):
                                        continue
                                    posts.append(parsed)
                                    new_count_net += 1
                                if new_count_net > 0:
                                    consecutive_dry = 0
                                else:
                                    consecutive_dry += 1
                            else:
                                consecutive_dry = 999  # always run DOM path when intercept off

                            # ── 2. DOM fallback (only when network is dry) ────
                            new_count_dom = 0
                            run_dom = (not self.cfg.network_intercept_mode
                                       or consecutive_dry > 3)
                            if run_dom:
                                feed_html = ""
                                try:
                                    self._click_see_more(page)
                                    self._find_post_elements(page)
                                    feed_html = self._safe_evaluate(
                                        page,
                                        "() => { "
                                        "  const ps = Array.from(document.querySelectorAll('[data-fw-post]')); "
                                        "  return ps.length "
                                        "    ? '<div>' + ps.map(el => el.outerHTML).join('') + '</div>' "
                                        "    : ''; "
                                        "}",
                                    )
                                except PWTimeoutError as _te:
                                    logger.warning(
                                        "[%s] DOM evaluate timed out at scroll %d: %s — restarting session",
                                        code, total_scrolls, _te,
                                    )
                                    break  # break inner loop → triggers restart
                                except Exception as _de:
                                    logger.warning(
                                        "[%s] DOM extract failed at scroll %d: %s",
                                        code, total_scrolls, _de,
                                    )

                                if feed_html:
                                    for parsed in DesktopHTMLParser.parse_feed_html(feed_html, seen_hashes):
                                        if self._is_comment_or_noise(parsed):
                                            continue
                                        posts.append(parsed)
                                        new_count_dom += 1

                                try:
                                    self._cleanup_dom(page)
                                except Exception:
                                    pass

                            new_count = new_count_net + new_count_dom
                            if new_count > 0:
                                stale_count = 0
                                last_progress_scroll = total_scrolls
                                last_scroll_progress_t = time.monotonic()
                                prefreeze_screenshot_taken = False
                                pbar.update(new_count)
                            elif network_alive:
                                # GraphQL traffic is still arriving — the page is
                                # alive, just dedup-saturated. Don't trip stale.
                                # (last_scroll_progress_t still resets so the
                                # 30s pre-freeze screenshot won't false-fire.)
                                last_scroll_progress_t = time.monotonic()
                                prefreeze_screenshot_taken = False
                            else:
                                stale_count += 1

                            # Unique-stale: scrolls since the dedupe set last
                            # grew, regardless of network_alive. Catches the
                            # case where Facebook keeps re-serving duplicates
                            # after a restart, or where the page is approaching
                            # freeze and stops yielding new content.
                            if len(seen_hashes) > last_unique_count:
                                last_unique_count = len(seen_hashes)
                                unique_stale_count = 0
                            else:
                                unique_stale_count += 1

                            pbar.set_postfix(
                                scroll=total_scrolls,
                                stale=stale_count,
                                ustale=unique_stale_count,
                                sess=restarter.cycles + 1,
                                net=extractor.responses_seen if self.cfg.network_intercept_mode else 0,
                            )

                            # ── 3. Periodic memory monitoring + pressure trigger ──
                            if total_scrolls > 0 and total_scrolls % self.cfg.memory_check_interval == 0:
                                self._cdp_gc(context, page)
                                self._log_heap(page, code, total_scrolls, extractor, len(posts))
                                # Heap-pressure early restart — far cheaper than
                                # waiting for the freeze. Read post-GC heap; if
                                # still over threshold, end session early.
                                try:
                                    mem = page.evaluate(
                                        "() => performance && performance.memory ? "
                                        "performance.memory.usedJSHeapSize : 0"
                                    )
                                    used_mb = (mem or 0) / (1024 * 1024)
                                    if used_mb > self.cfg.heap_pressure_mb:
                                        tqdm.write(
                                            f"[{code}] Heap pressure {used_mb:.0f}MB > "
                                            f"{self.cfg.heap_pressure_mb}MB — ending session early to restart"
                                        )
                                        heap_pressure_triggered = True
                                        break  # exit inner loop → restart cycle
                                except Exception:
                                    pass

                            # ── 4. Pre-freeze diagnostic screenshot ──────────
                            if (
                                not prefreeze_screenshot_taken
                                and (time.monotonic() - last_scroll_progress_t) > SAME_SCROLL_DWELL_SECS
                            ):
                                self._capture_prefreeze_screenshot(page, code, total_scrolls)
                                prefreeze_screenshot_taken = True

                            # ── 5. Time-debounced checkpoint ─────────────────
                            if new_count > 0:
                                _now = time.monotonic()
                                if _now - _last_checkpoint_t >= 30:
                                    self._checkpoint_save(posts, code)
                                    # Persist session state alongside posts so a
                                    # crash mid-session doesn't lose cursor data
                                    # — the next run resumes via cursor-aware
                                    # fast-forward instead of re-scraping the
                                    # entire duplicate prefix.
                                    last_permalink = None
                                    for p in reversed(posts):
                                        if p.get("post_url"):
                                            last_permalink = p["post_url"]
                                            break
                                    restarter.save(
                                        page, context, code, last_permalink,
                                        total_scrolls, len(posts),
                                        seen_cursors=extractor._cursors if extractor else None,
                                    )
                                    _last_checkpoint_t = _now
                                    tqdm.write(
                                        f"[{code}] Checkpoint: {len(posts)}/{self.cfg.target_posts} posts saved (scroll={total_scrolls})"
                                    )

                            # ── 6. Stop conditions ───────────────────────────
                            if len(posts) >= self.cfg.target_posts:
                                tqdm.write(f"[{code}] Target reached: {len(posts)} posts")
                                stop_outer = True
                                stop_reason = "target_reached"
                                break

                            if stale_count >= self.cfg.stale_scroll_limit:
                                # Don't stop hard yet — let the session-boundary
                                # logic decide whether a restart resurrects the feed.
                                tqdm.write(
                                    f"[{code}] {stale_count} stale scrolls — ending session early to attempt restart"
                                )
                                break

                            # Unique-stale guard: dedupe set hasn't grown in
                            # cfg.unique_stale_limit consecutive scrolls. This
                            # fires even when network_alive=True (which suppresses
                            # stale_count). Triggers on three real conditions:
                            # dedup-saturation post-restart, end-of-feed, or an
                            # approaching CDP/heap freeze where Chrome keeps
                            # serving the same posts. The session-restart logic
                            # decides whether to attempt recovery.
                            if unique_stale_count >= self.cfg.unique_stale_limit:
                                tqdm.write(
                                    f"[{code}] {unique_stale_count} unique-stale scrolls "
                                    f"(seen_hashes={len(seen_hashes)} unchanged) — ending session"
                                )
                                break

                            if not self.cfg.authenticated and self._is_login_blocked(page):
                                if modal_dismiss_count < self.cfg.max_modal_dismiss_attempts:
                                    self._dismiss_overlays(page, code)
                                    modal_dismiss_count += 1
                                    if self._is_login_blocked(page):
                                        tqdm.write(f"[{code}] Login wall impassable")
                                        stop_outer = True
                                        stop_reason = "login_wall"
                                        break
                                else:
                                    tqdm.write(f"[{code}] Max modal dismiss attempts reached")
                                    stop_outer = True
                                    stop_reason = "modal_loop"
                                    break

                            # ── 7. Scroll ─────────────────────────────────────
                            if stale_count > 20:
                                try:
                                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                    page.wait_for_timeout(2000)
                                    page.evaluate("window.scrollBy(0, -400)")
                                    page.wait_for_timeout(500)
                                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                except Exception:
                                    pass
                                random_sleep(self.cfg.scroll_delay_min, self.cfg.scroll_delay_max)
                            else:
                                try:
                                    page.evaluate(
                                        f"window.scrollBy(0, {self.cfg.scroll_pixels + random.randint(0, 500)})"
                                    )
                                    random_sleep(self.cfg.scroll_delay_min, self.cfg.scroll_delay_max)
                                except Exception as _scroll_err:
                                    logger.warning(
                                        "[%s] Scroll evaluate failed at scroll %d: %s — restarting session",
                                        code, total_scrolls, _scroll_err,
                                    )
                                    break  # trigger restart

                        # ── End of session ──────────────────────────────────────
                        if stop_outer:
                            break

                        # Did the session make progress? If not, count it. After
                        # 3 zero-progress sessions in a row, conclude end of feed.
                        if len(posts) == session_start_post_count:
                            sessions_without_progress += 1
                            logger.info(
                                "[%s] Session yielded 0 new posts (streak=%d)",
                                code, sessions_without_progress,
                            )
                            if sessions_without_progress >= 3:
                                tqdm.write(
                                    f"[{code}] 3 consecutive sessions without progress — feed exhausted"
                                )
                                stop_outer = True
                                stop_reason = "feed_exhausted"
                                break
                        else:
                            sessions_without_progress = 0

                        # ── Restart cycle ────────────────────────────────────
                        # Detach extractor before closing the old page.
                        if self.cfg.network_intercept_mode:
                            extractor.detach(page)

                        # Drop any cached CDP session for the old page.
                        self._cdp_sessions.pop(id(page), None)

                        try:
                            browser, context, page = restarter.cycle(
                                pw, browser, context, page, code, url,
                                extractor, total_scrolls, posts,
                            )
                        except Exception as exc:
                            logger.error(
                                "[%s] Restart cycle failed: %s — stopping",
                                code, exc,
                            )
                            stop_outer = True
                            stop_reason = "restart_failed"
                            break

                        # block_media route is re-armed inside restarter.cycle().
                        # extractor is re-attached inside restarter.cycle() for
                        # extractor-driven fast-forward.

                        self._dismiss_overlays(page, code)

                        # Stale counters reset on each new session — give the
                        # restarted page room to load posts before we judge it.
                        # last_unique_count is reset to current size so we
                        # measure growth from this point forward.
                        stale_count = 0
                        unique_stale_count = 0
                        last_unique_count = len(seen_hashes)

                except KeyboardInterrupt:
                    tqdm.write(
                        f"[{code}] Watchdog: page froze >90 s — "
                        f"saving {len(posts)} posts collected so far"
                    )
                    logger.warning(
                        "[%s] ScrollWatchdog fired — exiting scroll loop", code,
                    )
                finally:
                    watchdog.stop()
                    pbar.close()
                    if self.cfg.network_intercept_mode:
                        extractor.detach(page)

                logger.info(
                    "[%s] Scrape ended: reason=%s scrolls=%d posts=%d sessions=%d graphql_resp=%d bytes=%.2fmb",
                    code, stop_reason or "loop_exit", total_scrolls, len(posts),
                    restarter.cycles + 1, extractor.responses_seen,
                    extractor.bytes_seen / (1024 * 1024),
                )

            except Exception as exc:
                logger.error("[%s][desktop] Error during scraping: %s", code, exc)
            finally:
                self._cdp_sessions.clear()
                if browser is not None:
                    try:
                        browser.close()
                    except Exception:
                        pass
                else:
                    try:
                        context.close()
                    except Exception:
                        pass

        # Final flush so the JSONL is the complete record. Without this, the
        # last partial window (since the most recent 30s checkpoint) would
        # only live in the {code}.json deliverable; on resume tomorrow the
        # JSONL would be stale and we'd re-scrape that window.
        if posts:
            try:
                self._checkpoint_save(posts, code)
            except Exception as exc:
                logger.warning("[%s] Final checkpoint flush failed: %s", code, exc)

        return posts, seen_hashes

    def _capture_prefreeze_screenshot(self, page: Page, code: str, scroll_n: int) -> None:
        """Snap a debug PNG when a single scroll dwells beyond SAME_SCROLL_DWELL_SECS.

        Saves to scraper_project/debug_screenshots/. Always tolerated to fail —
        diagnostic-only.
        """
        try:
            os.makedirs(self.cfg.debug_screenshot_dir, exist_ok=True)
            path = os.path.join(
                self.cfg.debug_screenshot_dir,
                f"{code}_scroll{scroll_n:04d}_prefreeze.png",
            )
            page.screenshot(path=path, full_page=False, timeout=10_000)
            logger.warning(
                "[%s] Single scroll dwell >%.0fs at scroll %d — captured %s",
                code, SAME_SCROLL_DWELL_SECS, scroll_n, path,
            )
        except Exception as exc:
            logger.debug("Pre-freeze screenshot failed: %s", exc)

    # ── Checkpointing ────────────────────────────────────────────────────────

    def _checkpoint_path(self, code: str) -> str:
        return os.path.join(self.cfg.output_dir, f"{code}.jsonl")

    def _legacy_checkpoint_path(self, code: str) -> str:
        return os.path.join(self.cfg.output_dir, f"{code}_checkpoint.json")

    def _checkpoint_save(self, posts: list[dict], code: str) -> None:
        """Append-only JSONL checkpoint.

        One post per line; survives mid-write crashes (a torn final line is
        skipped on load). Tracks per-target written post_ids in memory so
        repeated calls only append the delta since the previous call.
        """
        path = self._checkpoint_path(code)
        os.makedirs(self.cfg.output_dir, exist_ok=True)
        written = self._jsonl_written_ids.setdefault(code, set())
        appended = 0
        with open(path, "a", encoding="utf-8") as f:
            for p in posts:
                pid = p.get("post_id") or post_hash(p.get("text", ""))[:16]
                if not pid or pid in written:
                    continue
                # Persist post_id back onto the dict so downstream consumers
                # see the same id we deduped against.
                p["post_id"] = pid
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
                written.add(pid)
                appended += 1
        if appended:
            logger.info(
                "[%s] Checkpoint: +%d new posts (total=%d) -> %s",
                code, appended, len(written), path,
            )

    def _checkpoint_load(self, code: str) -> list[dict]:
        """Read JSONL checkpoint, tolerating a torn final line.

        Migrates a legacy {code}_checkpoint.json once if present and the JSONL
        does not yet exist.
        """
        jsonl_path = self._checkpoint_path(code)
        legacy_path = self._legacy_checkpoint_path(code)

        if not os.path.exists(jsonl_path) and os.path.exists(legacy_path):
            try:
                with open(legacy_path, "r", encoding="utf-8") as f:
                    legacy = json.load(f)
                legacy_posts = legacy.get("posts") or []
                if legacy_posts:
                    os.makedirs(self.cfg.output_dir, exist_ok=True)
                    with open(jsonl_path, "w", encoding="utf-8") as f:
                        for p in legacy_posts:
                            pid = p.get("post_id") or post_hash(p.get("text", ""))[:16]
                            if not pid:
                                continue
                            p["post_id"] = pid
                            f.write(json.dumps(p, ensure_ascii=False) + "\n")
                    logger.info(
                        "[%s] Migrated legacy checkpoint: %d posts -> %s",
                        code, len(legacy_posts), jsonl_path,
                    )
            except Exception as exc:
                logger.warning("[%s] Legacy checkpoint migration failed: %s", code, exc)

        if not os.path.exists(jsonl_path):
            return []

        posts: list[dict] = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            try:
                posts.append(json.loads(line))
            except json.JSONDecodeError:
                # Tolerate a torn final line (mid-write crash). Anything mid-file
                # is unexpected; log and skip.
                if i == len(lines) - 1:
                    logger.warning("[%s] Skipping torn final checkpoint line", code)
                else:
                    logger.warning("[%s] Skipping malformed checkpoint line %d", code, i)
        return posts

    # ── Strategy 0: mbasic via httpx (freeze-proof primary) ───────────────────

    @staticmethod
    def _to_mbasic_url(url: str) -> str:
        """Transform a desktop FB URL into its mbasic equivalent."""
        import re as _re
        p_match = _re.search(r"facebook\.com/p/[^/]*?-(\d{10,})", url)
        if p_match:
            return f"https://mbasic.facebook.com/profile.php?id={p_match.group(1)}"
        return url.replace("www.facebook.com", "mbasic.facebook.com")

    def _cookies_to_httpx(self):
        """Convert Playwright-format cookies to an httpx.Cookies jar."""
        import httpx
        jar = httpx.Cookies()
        for c in self._cookies:
            domain = c.get("domain", "")
            if "facebook.com" not in domain:
                continue
            jar.set(
                c["name"],
                c["value"],
                domain=domain.lstrip("."),
                path=c.get("path", "/"),
            )
        return jar

    def _basic_mobile_strategy_httpx(self, url: str, code: str) -> list[dict]:
        """Pure-HTTP scrape of mbasic.facebook.com — no Playwright, no CDP, no V8.

        Eliminates the freeze cliff entirely on this path: every freeze cause
        (CDP IPC stall, DOM accumulation, V8 fragmentation) is in the browser,
        and there is no browser here. mbasic is server-rendered HTML; the
        existing BasicMobileParser already handles the same body Playwright
        would have produced via page.content().
        """
        try:
            import httpx
        except ImportError:
            logger.warning(
                "[%s][basic_mobile_httpx] httpx not installed — falling through to next strategy",
                code,
            )
            return []

        posts: list[dict] = []
        seen_hashes: set[str] = set()

        # Pre-load any prior checkpoint so we resume on the same JSONL stream
        # the desktop strategy would have used.
        try:
            for _p in self._checkpoint_load(code):
                _t = _p.get("text") or ""
                if not _t:
                    continue
                _h = post_hash(_t)
                if _h in seen_hashes:
                    continue
                seen_hashes.add(_h)
                _pid = _p.get("post_id") or _h[:16]
                _p["post_id"] = _pid
                self._jsonl_written_ids.setdefault(code, set()).add(_pid)
                posts.append(_p)
            if posts:
                logger.info(
                    "[%s][basic_mobile_httpx] Resumed checkpoint: %d posts pre-loaded",
                    code, len(posts),
                )
        except Exception as exc:
            logger.warning("[%s][basic_mobile_httpx] Resume failed: %s", code, exc)

        mobile_url = self._to_mbasic_url(url)
        cookies = self._cookies_to_httpx() if self._cookies else None
        if cookies:
            logger.info(
                "[%s][basic_mobile_httpx] Using %d cookies (authenticated)",
                code, len(self._cookies),
            )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Mobile Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        deadline = time.monotonic() + self.cfg.page_timeout_seconds
        max_pages = self.cfg.mbasic_max_pages
        pages_loaded = 0
        consecutive_empty = 0
        _last_checkpoint_t = time.monotonic()
        current_url: Optional[str] = mobile_url
        blocked = False

        try:
            with httpx.Client(
                cookies=cookies,
                headers=headers,
                follow_redirects=True,
                timeout=30.0,
                http2=False,
            ) as client:
                while current_url and pages_loaded < max_pages:
                    if time.monotonic() > deadline:
                        logger.info("[%s][basic_mobile_httpx] Timeout reached", code)
                        break

                    try:
                        resp = client.get(current_url)
                    except httpx.HTTPError as exc:
                        logger.warning(
                            "[%s][basic_mobile_httpx] Request failed: %s — falling through",
                            code, exc,
                        )
                        blocked = True
                        break

                    if resp.status_code >= 400:
                        logger.warning(
                            "[%s][basic_mobile_httpx] HTTP %d — falling through",
                            code, resp.status_code,
                        )
                        blocked = True
                        break

                    final_host = (resp.url.host or "").lower()
                    if final_host and final_host != "mbasic.facebook.com":
                        logger.warning(
                            "[%s][basic_mobile_httpx] Redirected to %s — falling through",
                            code, final_host,
                        )
                        blocked = True
                        break

                    body = resp.text or ""
                    # Block sentinels can appear deep in the body (mbasic's
                    # browser-not-supported template puts the message ~9 KB in
                    # after a wall of inline CSS). Scan the full body.
                    body_lower = body.lower()
                    if "not available on this browser" in body_lower:
                        logger.warning(
                            "[%s][basic_mobile_httpx] mbasic UA-gated (browser-not-supported page) — falling through",
                            code,
                        )
                        blocked = True
                        break
                    if (
                        "you must log in" in body_lower
                        or "/checkpoint/" in str(resp.url)
                        or "captcha" in body_lower
                    ):
                        logger.warning(
                            "[%s][basic_mobile_httpx] Login/checkpoint wall — falling through",
                            code,
                        )
                        blocked = True
                        break

                    page_posts, next_url = BasicMobileParser.parse_page(body)

                    new_count = 0
                    for p in page_posts:
                        h = post_hash(p.get("text", ""))
                        if h in seen_hashes:
                            continue
                        seen_hashes.add(h)
                        p["post_id"] = h[:16]
                        posts.append(p)
                        new_count += 1

                    pages_loaded += 1
                    logger.info(
                        "[%s][basic_mobile_httpx] Page %d: +%d new (total %d)",
                        code, pages_loaded, new_count, len(posts),
                    )

                    # Time-debounced checkpoint (matches desktop cadence).
                    _now = time.monotonic()
                    if new_count > 0 and (_now - _last_checkpoint_t) >= 30:
                        self._checkpoint_save(posts, code)
                        _last_checkpoint_t = _now

                    if len(posts) >= self.cfg.target_posts:
                        logger.info("[%s][basic_mobile_httpx] Target reached", code)
                        break

                    if new_count == 0:
                        consecutive_empty += 1
                        if consecutive_empty >= 2:
                            logger.info(
                                "[%s][basic_mobile_httpx] Two consecutive empty pages — stopping",
                                code,
                            )
                            break
                    else:
                        consecutive_empty = 0

                    if not next_url:
                        logger.info("[%s][basic_mobile_httpx] No next-link — feed exhausted", code)
                        break

                    current_url = next_url
                    random_sleep(
                        self.cfg.mbasic_request_delay_min,
                        self.cfg.mbasic_request_delay_max,
                    )
        except Exception as exc:
            logger.error("[%s][basic_mobile_httpx] Error: %s", code, exc)

        # Final flush to JSONL so the next strategy (if any) sees them too.
        if posts:
            self._checkpoint_save(posts, code)

        if blocked:
            logger.info(
                "[%s][basic_mobile_httpx] Blocked path — %d posts collected before fallthrough",
                code, len(posts),
            )

        return posts

    # ── Strategy 2: mbasic (Basic Mobile) ────────────────────────────────────

    def _basic_mobile_strategy(self, url: str, code: str) -> list[dict]:
        posts: list[dict] = []
        seen_hashes: set[str] = set()

        # /p/PageName-NUMERIC_ID/ format — mbasic needs profile.php?id=NUMERIC_ID
        import re as _re
        p_match = _re.search(r"facebook\.com/p/[^/]*?-(\d{10,})", url)
        if p_match:
            mobile_url = f"https://mbasic.facebook.com/profile.php?id={p_match.group(1)}"
        else:
            mobile_url = url.replace("www.facebook.com", "mbasic.facebook.com")

        with sync_playwright() as pw:
            _mobile_args = ["--disable-blink-features=AutomationControlled"]
            if self.cfg.headed:
                _mobile_args.append("--start-maximized")
            browser = pw.chromium.launch(
                headless=self.cfg.headless,
                channel=self.cfg.browser_channel,
                args=_mobile_args,
                ignore_default_args=["--enable-automation"],
                **self._headed_launch_kwargs(),
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Mobile Safari/537.36"
                ),
                viewport={"width": 412, "height": 915},
                locale="en-US",
            )

            if self._cookies:
                context.add_cookies(self._cookies)
                logger.info("[%s][basic_mobile] Injected %d session cookies", code, len(self._cookies))

            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            current_url: Optional[str] = mobile_url
            pages_loaded = 0
            max_pages = 200 if self.cfg.authenticated else 50
            deadline = time.monotonic() + self.cfg.page_timeout_seconds

            try:
                while current_url and pages_loaded < max_pages:
                    if time.monotonic() > deadline:
                        logger.info("[%s][basic_mobile] Timeout reached", code)
                        break

                    logger.info("[%s][basic_mobile] Loading page %d", code, pages_loaded + 1)
                    page.goto(current_url, timeout=self.cfg.page_load_timeout, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)

                    page_content = page.content()
                    if not self.cfg.authenticated and (
                        "you must log in" in page_content.lower()
                        or self._is_login_blocked(page)
                    ):
                        logger.info("[%s][basic_mobile] Login required — stopping", code)
                        break

                    page_posts, next_url = BasicMobileParser.parse_page(page_content)

                    new_count = 0
                    for p in page_posts:
                        h = post_hash(p.get("text", ""))
                        if h not in seen_hashes:
                            seen_hashes.add(h)
                            p["post_id"] = h[:16]
                            posts.append(p)
                            new_count += 1

                    logger.info(
                        "[%s][basic_mobile] Page %d: +%d new (total %d)",
                        code, pages_loaded + 1, new_count, len(posts),
                    )

                    if len(posts) >= self.cfg.target_posts:
                        logger.info("[%s][basic_mobile] Target reached", code)
                        break

                    if new_count == 0:
                        logger.info("[%s][basic_mobile] No new posts on this page — stopping", code)
                        break

                    current_url = next_url
                    pages_loaded += 1
                    random_sleep(self.cfg.scroll_delay_min, self.cfg.scroll_delay_max)

            except Exception as exc:
                logger.error("[%s][basic_mobile] Error: %s", code, exc)
            finally:
                browser.close()

        return posts

    # ── Page navigation ───────────────────────────────────────────────────────

    def _navigate_to_posts_tab(self, page: Page, code: str) -> None:
        """Click the 'Posts' tab on a Facebook page to ensure we're viewing posts."""
        posts_selectors = [
            "a[href*='/posts']",
            "a:has-text('Posts')",
            "span:has-text('Posts')",
        ]
        for sel in posts_selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=2000):
                    el.click()
                    logger.info("[%s][desktop] Clicked Posts tab via %s", code, sel)
                    page.wait_for_timeout(3000)
                    return
            except Exception:
                continue

    # ── Post element detection ────────────────────────────────────────────────

    def _find_post_elements(self, page: Page) -> list:
        """Find post container elements in the feed.

        Facebook's authenticated view does NOT use [role='article'] for posts —
        only for comments and Messenger messages. Posts are plain DIVs inside a
        feed container with many children. This method finds the feed container
        by structure, marks post children with a data attribute, then selects them.

        Stall protection is provided by the 90 s ScrollWatchdog (ctypes injection).
        Playwright Python's page.evaluate() does not accept a per-call timeout.
        """
        self._safe_evaluate(page, """() => {
            // Clear previous post markers
            document.querySelectorAll('[data-fw-post]').forEach(
                el => el.removeAttribute('data-fw-post')
            );

            // Scan for feed container by DOM structure.
            // Capped at 500 divs: the feed container is always near the top of
            // [role="main"] so 500 is sufficient for initial detection, while
            // preventing a 90-s CPU freeze when run on a 5000+ div DOM.
            // offsetWidth/offsetHeight are used instead of getBoundingClientRect()
            // to avoid a forced full layout reflow on every call.
            const scanForFeed = () => {
                const main = document.querySelector('[role="main"]');
                if (!main) return null;
                const candidates = main.querySelectorAll('div');
                let checked = 0;
                for (const div of candidates) {
                    if (++checked > 500) break;
                    const children = Array.from(div.children);
                    if (children.length < 8) continue;
                    const visible = children.filter(c => c.offsetHeight > 50 && c.offsetWidth > 400);
                    if (visible.length < 5) continue;
                    const widths = visible.map(c => c.offsetWidth);
                    const mode = widths.slice().sort((a,b) => a-b)[Math.floor(widths.length/2)];
                    const consistent = widths.filter(w => Math.abs(w - mode) < 50).length;
                    if (consistent >= visible.length * 0.7) {
                        return div;
                    }
                }
                return null;
            };

            const markPosts = (container) => {
                let count = 0;
                if (!container) return 0;
                for (const child of container.children) {
                    if (child.hasAttribute('data-fw-seen')) continue;
                    if (child.hasAttribute('data-fw-placeholder')) continue;
                    const h = child.offsetHeight;
                    if (h < 100 || child.offsetWidth < 400) continue;
                    const text = child.textContent || '';
                    if (text.length < 30) continue;
                    if (text.includes('Message sent') || text.includes('end-to-end encryption')) continue;
                    child.setAttribute('data-fw-post', String(count++));
                    child.setAttribute('data-fw-height', String(h));  // cache for cleanup
                }
                return count;
            };

            // data-fw-noscan: set on document.body when the cached feed container
            // is found to be detached (Facebook rebuilds it around 60-70 posts).
            // Running scanForFeed on a 5000+ div DOM at that point causes a CPU
            // spike to 90%+ and freezes Chrome completely.
            //
            // Protocol:
            //   Scroll N   — detachment detected → set noscan, use article fallback
            //   Scroll N+1 — noscan present → clear it, use article fallback again
            //   Scroll N+2 — no cache, no noscan → fresh scanForFeed (cap=500)
            //                  → finds rebuilt container → normal operation resumes
            if (document.body.hasAttribute('data-fw-noscan')) {
                document.body.removeAttribute('data-fw-noscan');
                // Fall through to [role="article"] fallback below
            } else {
                let feedContainer = document.querySelector('[data-fw-feed]');

                if (feedContainer) {
                    if (!document.body.contains(feedContainer)) {
                        // Detached — clear cache, arm noscan for next scroll,
                        // fall through to article fallback this scroll.
                        feedContainer.removeAttribute('data-fw-feed');
                        document.body.setAttribute('data-fw-noscan', '1');
                    } else {
                        // Container intact — mark new posts and return.
                        // Skip article fallback entirely when we have the feed
                        // container to avoid incorrectly marking comment articles.
                        markPosts(feedContainer);
                        return;
                    }
                } else {
                    // No cache yet — initial scan or post-noscan re-discovery.
                    // Large-DOM guard: skip scanForFeed entirely if the document
                    // has accumulated > 2000 divs. scanForFeed walks
                    // [role="main"] querySelectorAll('div') and even with the
                    // 500-iteration cap, the initial selector match itself
                    // scales with full DOM size and freezes Chrome around
                    // scroll 60-70. Article fallback handles this scroll;
                    // the next scroll (after cleanup) will retry the scan.
                    if (document.querySelectorAll('div').length > 2000) {
                        // fall through to article fallback below
                    } else {
                        feedContainer = scanForFeed();
                        if (feedContainer) {
                            feedContainer.setAttribute('data-fw-feed', '1');
                            markPosts(feedContainer);
                            return;  // skip article fallback — we're in feed mode
                        }
                    }
                }
            }

            // Fallback: unauthenticated mode uses [role="article"] for posts.
            // Also used during the 2-scroll cool-off after a container detachment.
            let artCount = 0;
            const articles = document.querySelectorAll('[role="article"]');
            for (const art of articles) {
                if (art.parentElement && art.parentElement.closest('[role="article"]')) {
                    continue;  // skip nested articles (comment replies)
                }
                art.setAttribute('data-fw-post', String(artCount++));
            }
        }""")

        return page.query_selector_all("[data-fw-post]")

    def _click_see_more(self, page: Page) -> None:
        """Expand truncated posts by clicking all visible 'See more' buttons in the feed."""
        try:
            self._safe_evaluate(page, """() => {
                const feed = document.querySelector('[data-fw-feed]');
                // Only use [role="main"] as scope if we have a feed container — using
                // [role="main"] directly iterates its entire subtree which is huge.
                const scope = feed || null;
                if (!scope) return;
                // Scope to unseen posts only; use textContent (no reflow).
                Array.from(scope.children)
                    .filter(c => !c.hasAttribute('data-fw-seen'))
                    .forEach(post => {
                        post.querySelectorAll('div[role="button"], span[role="button"]').forEach(btn => {
                            const t = (btn.textContent || '').trim().toLowerCase();
                            if (t === 'see more' || t === 'see more...') btn.click();
                        });
                    });
            }""")
            page.wait_for_timeout(200)
        except Exception:
            pass

    def _cleanup_dom(self, page: Page) -> int:
        """Mark parsed posts as seen and free their DOM memory.

        Returns the count of posts cleaned this scroll (for headed-mode
        diagnostics). Returns 0 on any evaluate failure.

        Two-part cleanup per processed post:
        1. Mark data-fw-seen / data-fw-placeholder so _find_post_elements
           and _click_see_more skip them on all future scroll iterations.
        2. Clear innerHTML to reclaim Chrome heap memory from accumulated
           post content (~500 KB raw HTML per post; 139 posts = ~70 MB).
           Without this Chrome approaches OOM and freezes the process.

        Height is read from data-fw-height (set by markPosts) to preserve
        page total height so Facebook's lazy-loader keeps scrolling correctly.

        WHY innerHTML='' and NOT replaceWith/remove:
          replaceWith/remove mutates the feed container's childNodes list,
          which fires React's mutation observer on the container itself →
          React reconciliation cascade over ALL siblings → Chrome main thread
          frozen for minutes. Cost scales with feed container child count;
          by scroll 200+ with thousands of placeholders, each replaceChild
          takes >90 s. innerHTML='' only mutates the post element's own
          subtree (a child the container manages, not the container's
          childList), so React does not reconcile the feed container.
          The original freeze at scroll 40-65 was caused by the 512 MB V8
          heap cap (--max_old_space_size=512) running out before innerHTML=''
          could free enough memory. Raising the heap to 2048 MB (js_heap_size_mb)
          is the primary fix; innerHTML='' is the correct cleanup method.
        """
        try:
            count = self._safe_evaluate(page, """() => {
                const posts = document.querySelectorAll('[data-fw-post]');
                posts.forEach(el => {
                    el.removeAttribute('data-fw-post');
                    el.setAttribute('data-fw-seen', '1');
                    el.setAttribute('data-fw-placeholder', '1');
                    const h = parseInt(el.getAttribute('data-fw-height') || '300', 10);
                    el.innerHTML = '';
                    el.style.minHeight = h + 'px';
                });
                return posts.length;
            }""")
            return int(count or 0)
        except Exception:
            return 0

    def _debug_capture(self, page: Page, scroll_i: int, code: str) -> None:
        """Capture screenshot + DOM/heap diagnostics on scrolls 35-70 every 5.

        No-op unless self.cfg.debug_screenshots is True. Wraps the whole capture
        in try/except so any failure (page closed, slow snapshot, etc.) cannot
        break the scroll loop. Saves PNGs to self.cfg.debug_screenshot_dir.
        """
        if not self.cfg.debug_screenshots:
            return
        if scroll_i < 35 or scroll_i > 70 or scroll_i % 5 != 0:
            return
        try:
            os.makedirs(self.cfg.debug_screenshot_dir, exist_ok=True)
            shot_path = os.path.join(
                self.cfg.debug_screenshot_dir,
                f"scroll_{scroll_i:03d}_{code}.png",
            )
            page.screenshot(path=shot_path, full_page=False, timeout=10_000)
            stats = self._safe_evaluate(
                page,
                """() => {
                    const feed = document.querySelector('[data-fw-feed]');
                    const heap = (performance && performance.memory)
                        ? performance.memory.usedJSHeapSize : null;
                    return {
                        bodyChildren: document.body.children.length,
                        divCount: document.querySelectorAll('div').length,
                        feedDetached: feed ? !document.body.contains(feed) : 'no-feed',
                        heap: heap,
                    };
                }""",
            )
            heap_mb = (
                round(stats["heap"] / (1024 * 1024), 1)
                if stats and stats.get("heap") else "n/a"
            )
            logger.info(
                "[%s] DEBUG scroll=%d body_children=%s divs=%s feed_detached=%s heap_MB=%s shot=%s",
                code, scroll_i,
                stats.get("bodyChildren") if stats else "?",
                stats.get("divCount") if stats else "?",
                stats.get("feedDetached") if stats else "?",
                heap_mb,
                shot_path,
            )
        except Exception as _exc:
            logger.warning("[%s] _debug_capture scroll=%d failed: %s", code, scroll_i, _exc)

    # ── Overlay handling ─────────────────────────────────────────────────────

    def _dismiss_chat_popups(self, page: Page, code: str) -> None:
        """Close Messenger chat tabs and comment-thread overlays that pin to
        the bottom-right and absorb scroll events.

        Symptoms: scrolls advance the chat box but not the underlying feed,
        page.evaluate stalls because focus is captured by the modal, and
        graphql still fires (polluting dedupe with chat traffic).

        Runs purely in JS via a single page.evaluate so it's cheap; the close
        buttons it targets are stable Comet selectors.
        """
        try:
            self._safe_evaluate(page, r"""() => {
                // 1. Messenger chat tab close buttons.
                // Each open chat tab is a div with aria-label like "Close chat" / "Minimize chat"
                document.querySelectorAll(
                    'div[role="button"][aria-label^="Close chat"], '
                    + 'div[role="button"][aria-label^="Minimize chat"], '
                    + 'div[aria-label="Close tab"][role="button"]'
                ).forEach(b => { try { b.click(); } catch(e) {} });

                // 2. Comet comment-thread side dialogs (the "Comment as X" expanded view).
                // These are dialogs with a Close button in the header.
                document.querySelectorAll('div[role="dialog"]').forEach(d => {
                    const txt = (d.getAttribute('aria-label') || '').toLowerCase();
                    if (txt.includes('comment') || txt.includes('post')
                            || txt.includes('messenger') || txt.includes('chat')) {
                        const close = d.querySelector(
                            '[aria-label="Close"][role="button"], '
                            + 'div[aria-label="Close"]'
                        );
                        if (close) { try { close.click(); } catch(e) {} }
                    }
                });

                // 3. Stop any focus-captured input from absorbing scroll events.
                // Blurring active editable element re-routes scrolls to the feed.
                try {
                    const a = document.activeElement;
                    if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA'
                            || a.getAttribute('contenteditable') === 'true')) {
                        a.blur();
                    }
                } catch(e) {}
            }""")
        except Exception as exc:
            logger.debug("[%s] Chat popup dismissal failed: %s", code, exc)

    def _dismiss_overlays(self, page: Page, code: str) -> None:
        # Pure CSS attribute selectors only — no :has-text() which forces a full
        # JS text scan across Facebook's large DOM (~3 s per selector).
        cookie_selectors = [
            "button[data-cookiebanner='accept_button']",
            "button[title='Allow all cookies']",
            "button[title='Allow essential and optional cookies']",
        ]
        for sel in cookie_selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=0):
                    btn.click()
                    logger.info("[%s] Dismissed cookie consent via %s", code, sel)
                    page.wait_for_timeout(500)
                    break
            except Exception:
                continue

        close_selectors = [
            "div[role='dialog'] [aria-label='Close']",
            "[aria-label='Close'][role='button']",
        ]
        for sel in close_selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=0):
                    btn.click()
                    logger.info("[%s] Dismissed login modal via %s", code, sel)
                    page.wait_for_timeout(500)
                    break
            except Exception:
                continue

        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass

    def _is_login_blocked(self, page: Page) -> bool:
        block_indicators = [
            "div[role='dialog'][aria-label*='log in']",
            "div[role='dialog'][aria-label*='Log In']",
            "div[role='dialog'][aria-label*='Sign Up']",
            "div[role='dialog'][aria-label*='Facebook']",
        ]
        for sel in block_indicators:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=1000):
                    box = el.bounding_box()
                    if box and box["height"] > 300:
                        return True
            except Exception:
                continue

        try:
            login_form = page.locator("form[action*='login']").first
            if login_form.is_visible(timeout=1000):
                box = login_form.bounding_box()
                if box and box["height"] > 200:
                    return True
        except Exception:
            pass

        return False

    @staticmethod
    def _is_comment_or_noise(parsed: dict) -> bool:
        url = parsed.get("post_url", "") or ""
        if "comment_id=" in url or "reply_comment_id=" in url:
            return True

        text = parsed.get("text", "")
        messenger_signals = (
            "Message sent",
            "end-to-end encryption",
            "Enter, Message sent",
            "You replied to",
            "Sent\nEnter",
        )
        if any(sig in text for sig in messenger_signals):
            return True

        lines = text.strip().split("\n")
        if len(lines) >= 2:
            last_line = lines[-1].strip().lower()
            if last_line in ("reply", "reply...") or last_line.startswith("reply"):
                if "Reply" in lines[-1] and len(text) < 200:
                    return True

        return False
