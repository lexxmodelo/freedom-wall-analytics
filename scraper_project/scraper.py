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

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from tqdm import tqdm

from config import ScraperConfig
from parser import DesktopHTMLParser, DesktopParser, BasicMobileParser
from utils import random_sleep, deduplicate_posts, post_hash

logger = logging.getLogger("fw_scraper")


class FacebookScraper:
    """Orchestrates scraping of a single Facebook page."""

    def __init__(self, config: ScraperConfig):
        self.cfg = config
        self._cookies: list[dict] = []
        self._session_state: dict = {}   # localStorage saved by extract_cookies.py
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

        The ScrollWatchdog already handles stall timeouts; this wrapper just
        provides a uniform call signature across both the worktree and production
        scraper so shared helper methods (e.g. _find_post_elements) work in both.
        """
        if arg is not None:
            return page.evaluate(script, arg)
        return page.evaluate(script)

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
        if strategy == "desktop":
            return self._desktop_strategy(url, code)
        if strategy == "basic_mobile":
            return self._basic_mobile_strategy(url, code)
        logger.warning("Unknown strategy: %s", strategy)
        return []

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
        import tempfile
        posts: list[dict] = []
        seen_hashes: set[str] = set()

        with sync_playwright() as pw:
            browser: Optional[Browser] = None
            context: BrowserContext
            _context_is_fallback = False   # True when profile corrupted → new_context() used

            if self.cfg.use_persistent_context:
                if not self.cfg.persistent_profile_dir:
                    self.cfg.persistent_profile_dir = os.path.join(
                        tempfile.gettempdir(), "fb_login_profile"
                    )
                # Remove stale lock files left by previously force-killed Chrome instances.
                # Chrome exits immediately (exitCode=21) if it finds these.
                for _lock in ("SingletonLock", "SingletonSocket", "SingletonCookie", "lockfile"):
                    _lp = os.path.join(self.cfg.persistent_profile_dir, _lock)
                    try:
                        os.remove(_lp)
                        logger.info("[%s] Removed stale lock: %s", code, _lock)
                    except FileNotFoundError:
                        pass
                    except Exception:
                        pass
                logger.info(
                    "[%s][desktop] Persistent profile: %s", code, self.cfg.persistent_profile_dir
                )
                try:
                    context = pw.chromium.launch_persistent_context(
                        self.cfg.persistent_profile_dir,
                        headless=self.cfg.headless,
                        channel=self.cfg.browser_channel,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--disable-background-networking",
                            "--disable-sync",
                            "--disable-notifications",
                            "--disable-translate",
                            "--disable-default-apps",
                            "--js-flags=--max_old_space_size=512",
                        ],
                        ignore_default_args=["--enable-automation"],
                        viewport={
                            "width": self.cfg.viewport_width,
                            "height": self.cfg.viewport_height,
                        },
                        user_agent=self.cfg.user_agent,
                        locale="en-US",
                    )
                    logger.info("[%s][desktop] Persistent context launched", code)
                except Exception as _pctx_err:
                    logger.warning(
                        "[%s] Persistent context failed (%s) -- profile corrupted, deleting and retrying",
                        code, type(_pctx_err).__name__,
                    )
                    # Delete the corrupted profile so it can be rebuilt cleanly
                    # on the next extract_cookies.py run.
                    import shutil
                    try:
                        shutil.rmtree(self.cfg.persistent_profile_dir, ignore_errors=True)
                        os.makedirs(self.cfg.persistent_profile_dir, exist_ok=True)
                        logger.info("[%s] Deleted corrupted profile -- will use fresh persistent context + cookies", code)
                    except Exception as _del_err:
                        logger.warning("[%s] Could not delete profile: %s", code, _del_err)

                    _common_args = [
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--disable-background-networking",
                        "--disable-sync",
                        "--disable-notifications",
                        "--disable-translate",
                        "--disable-default-apps",
                        "--js-flags=--max_old_space_size=512",
                    ]
                    # Try fresh persistent context first (better than plain new_context)
                    try:
                        context = pw.chromium.launch_persistent_context(
                            self.cfg.persistent_profile_dir,
                            headless=self.cfg.headless,
                            channel=self.cfg.browser_channel,
                            args=_common_args,
                            ignore_default_args=["--enable-automation"],
                            viewport={
                                "width": self.cfg.viewport_width,
                                "height": self.cfg.viewport_height,
                            },
                            user_agent=self.cfg.user_agent,
                            locale="en-US",
                        )
                        if self._cookies:
                            context.add_cookies(self._cookies)
                            logger.info(
                                "[%s][desktop] Fresh persistent context -- injected %d cookies",
                                code, len(self._cookies),
                            )
                    except Exception as _pctx_err2:
                        # Last resort: plain browser + new_context
                        _context_is_fallback = True
                        logger.warning("[%s] Fresh persistent context also failed -- falling back to browser.new_context()", code)
                        browser = pw.chromium.launch(
                            headless=self.cfg.headless,
                            channel=self.cfg.browser_channel,
                            args=_common_args,
                            ignore_default_args=["--enable-automation"],
                        )
                        context = browser.new_context(
                            viewport={
                                "width": self.cfg.viewport_width,
                                "height": self.cfg.viewport_height,
                            },
                            user_agent=self.cfg.user_agent,
                            locale="en-US",
                        )
                        if self._cookies:
                            context.add_cookies(self._cookies)
                            logger.info(
                                "[%s][desktop] Injected %d cookies (last-resort mode)", code, len(self._cookies)
                            )
                        else:
                            logger.warning(
                                "[%s][desktop] No cookies -- session will be unauthenticated", code
                            )
            else:
                browser = pw.chromium.launch(
                    headless=self.cfg.headless,
                    channel=self.cfg.browser_channel,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--disable-background-networking",
                        "--disable-sync",
                        "--disable-notifications",
                        "--js-flags=--max_old_space_size=512",
                    ],
                    ignore_default_args=["--enable-automation"],
                )
                context = browser.new_context(
                    viewport={
                        "width": self.cfg.viewport_width,
                        "height": self.cfg.viewport_height,
                    },
                    user_agent=self.cfg.user_agent,
                    locale="en-US",
                )
                if self._cookies:
                    context.add_cookies(self._cookies)
                    logger.info("[%s][desktop] Injected %d session cookies", code, len(self._cookies))

            if self.cfg.block_media:
                context.route(
                    "**/*.{png,jpg,jpeg,gif,svg,mp4,webm,webp,ico,woff,woff2}",
                    lambda route: route.abort(),
                )

            page: Page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            try:
                logger.info("[%s][desktop] Navigating to %s", code, url)
                page.goto(url, timeout=self.cfg.page_load_timeout, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                # Restore localStorage from the saved session state (extract_cookies.py output).
                # Must run after page.goto() — localStorage is domain-scoped.
                # This is what allows the infinite scroll to keep working past ~100 posts
                # in fallback (cookie-only) mode.
                self._restore_session_state(page)

                # After profile corruption → last-resort new_context() fallback, capture
                # fresh localStorage and overwrite cookies_state.json so the next run
                # starts with valid state instead of stale/missing data.
                if _context_is_fallback and self.cfg.cookie_file:
                    try:
                        fresh_ls = page.evaluate(
                            "() => { const o = {}; "
                            "for (let i = 0; i < localStorage.length; i++) { "
                            "  const k = localStorage.key(i); "
                            "  o[k] = localStorage.getItem(k); "
                            "} return o; }"
                        )
                        if fresh_ls:
                            state_path = os.path.splitext(self.cfg.cookie_file)[0] + "_state.json"
                            with open(state_path, "w", encoding="utf-8") as _sf:
                                json.dump({"localStorage": fresh_ls}, _sf)
                            self._session_state = {"localStorage": fresh_ls}
                            logger.info(
                                "[%s] Refreshed cookies_state.json with %d keys (fallback mode)",
                                code, len(fresh_ls),
                            )
                    except Exception as _rs_err:
                        logger.warning("[%s] Could not refresh cookies_state.json: %s", code, _rs_err)

                # Detect if Facebook redirected to a login / checkpoint page.
                # This happens when cookies are expired or the session is invalid.
                current_url = page.url
                if any(kw in current_url for kw in ("login", "checkpoint", "recover", "disabled")):
                    logger.error(
                        "[%s] Facebook redirected to auth page (%s) -- "
                        "cookies may be expired. Re-run extract_cookies.py.",
                        code, current_url,
                    )
                    tqdm.write(
                        f"[{code}] ERROR: Facebook redirected to login page. "
                        f"Cookies expired -- run 'python extract_cookies.py' to log in again."
                    )
                    return posts, seen_hashes

                self._dismiss_overlays(page, code)
                page.wait_for_timeout(2000)

                self._navigate_to_posts_tab(page, code)

                stale_count = 0
                modal_dismiss_count = 0
                last_checkpoint = 0
                _last_checkpoint_t = time.monotonic()   # for time-debounced checkpoints
                deadline = time.monotonic() + self.cfg.page_timeout_seconds

                pbar = tqdm(
                    total=self.cfg.target_posts,
                    desc=f"[{code}]",
                    unit="post",
                    dynamic_ncols=True,
                )
                pbar.set_postfix(scroll=0, stale=0)

                # Watchdog: if a single iteration takes > 90 s (page.evaluate froze),
                # inject KeyboardInterrupt into the main thread so we exit cleanly
                # instead of hanging forever.  The watchdog does NOT call Playwright —
                # it only uses ctypes, which is safe from any thread.
                watchdog = self._ScrollWatchdog(timeout_secs=90)
                try:
                    for scroll_i in range(self.cfg.max_scroll_attempts):
                        watchdog.heartbeat()   # reset 90-s timer each iteration

                        if time.monotonic() > deadline:
                            tqdm.write(f"[{code}][desktop] Timeout after {scroll_i} scrolls")
                            break

                        # Dismiss at scroll 3 (catches the "Continue as X?" modal that
                        # appears a few seconds after page load), then every 30 scrolls
                        # in unauthenticated mode only (auth sessions rarely need it).
                        if scroll_i == 3 or (not self.cfg.authenticated and scroll_i > 0 and scroll_i % 30 == 0):
                            self._dismiss_overlays(page, code)

                        try:
                            self._click_see_more(page)
                            # Mark posts with data-fw-post (side-effect only; return value
                            # discarded — BS4 reads the same marks from the HTML snapshot).
                            self._find_post_elements(page)
                            # Snapshot only the marked posts — much smaller than full
                            # [role="main"].outerHTML which can be megabytes of HTML and
                            # stalls the CDP channel for >90 s on large feeds.
                            feed_html = self._safe_evaluate(
                                page,
                                "() => { "
                                "  const posts = Array.from(document.querySelectorAll('[data-fw-post]')); "
                                "  return posts.length "
                                "    ? '<div>' + posts.map(el => el.outerHTML).join('') + '</div>' "
                                "    : ''; "
                                "}",
                            )
                        except TimeoutError as _te:
                            tqdm.write(f"[{code}] Page unresponsive at scroll {scroll_i} ({_te}) — stopping")
                            break
                        new_count = 0
                        if feed_html:
                            for parsed in DesktopHTMLParser.parse_feed_html(feed_html, seen_hashes):
                                if self._is_comment_or_noise(parsed):
                                    continue
                                posts.append(parsed)
                                new_count += 1

                        # Mark seen in DOM so next scroll skips already-processed posts
                        self._cleanup_dom(page)

                        if new_count > 0:
                            stale_count = 0
                            pbar.update(new_count)
                        else:
                            stale_count += 1

                        pbar.set_postfix(scroll=scroll_i + 1, stale=stale_count)

                        # Checkpoint on every scroll that yields new posts,
                        # time-debounced to at most once every 30 s.
                        # This limits crash data loss to <30 s of scraping.
                        if new_count > 0:
                            _now = time.monotonic()
                            if _now - _last_checkpoint_t >= 30:
                                self._checkpoint_save(posts, code)
                                _last_checkpoint_t = _now
                                last_checkpoint = len(posts)
                                tqdm.write(
                                    f"[{code}] Checkpoint: {len(posts)}/{self.cfg.target_posts} posts saved"
                                )

                        if len(posts) >= self.cfg.target_posts:
                            tqdm.write(f"[{code}] Target reached: {len(posts)} posts")
                            break

                        if stale_count >= self.cfg.stale_scroll_limit:
                            tqdm.write(
                                f"[{code}] No new posts after {stale_count} scrolls — stopping"
                            )
                            break

                        if not self.cfg.authenticated and self._is_login_blocked(page):
                            if modal_dismiss_count < self.cfg.max_modal_dismiss_attempts:
                                self._dismiss_overlays(page, code)
                                modal_dismiss_count += 1
                                if self._is_login_blocked(page):
                                    tqdm.write(f"[{code}] Login wall impassable")
                                    break
                            else:
                                tqdm.write(f"[{code}] Max modal dismiss attempts reached")
                                break

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
                                page.evaluate(f"window.scrollBy(0, {self.cfg.scroll_pixels + random.randint(0, 500)})")
                                random_sleep(self.cfg.scroll_delay_min, self.cfg.scroll_delay_max)
                            except Exception as _scroll_err:
                                logger.warning("[%s] Scroll evaluate timed out or failed: %s", code, _scroll_err)
                                break
                except KeyboardInterrupt:
                    tqdm.write(
                        f"[{code}] Watchdog: page froze >90 s — "
                        f"saving {len(posts)} posts collected so far"
                    )
                    logger.warning(
                        "[%s] ScrollWatchdog fired — page.evaluate stalled >90 s, exiting scroll loop",
                        code,
                    )
                finally:
                    watchdog.stop()
                    pbar.close()

            except Exception as exc:
                logger.error("[%s][desktop] Error during scraping: %s", code, exc)
            finally:
                if browser:
                    browser.close()
                else:
                    context.close()

        return posts, seen_hashes

    # ── Checkpointing ────────────────────────────────────────────────────────

    def _checkpoint_save(self, posts: list[dict], code: str) -> None:
        """Write current posts to disk for crash recovery."""
        path = os.path.join(self.cfg.output_dir, f"{code}_checkpoint.json")
        os.makedirs(self.cfg.output_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"posts": posts}, f, ensure_ascii=False, indent=2)
        logger.info("[%s] Checkpoint: %d posts -> %s", code, len(posts), path)

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
            browser = pw.chromium.launch(
                headless=self.cfg.headless,
                channel=self.cfg.browser_channel,
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
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
                    feedContainer = scanForFeed();
                    if (feedContainer) {
                        feedContainer.setAttribute('data-fw-feed', '1');
                        markPosts(feedContainer);
                        return;  // skip article fallback — we're in feed mode
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

    def _cleanup_dom(self, page: Page) -> None:
        """Mark parsed posts as seen and free their DOM memory.

        Two-part cleanup per processed post:
        1. Mark data-fw-seen / data-fw-placeholder so _find_post_elements
           and _click_see_more skip them on all future scroll iterations.
        2. Clear innerHTML to reclaim Chrome heap memory from accumulated
           post content (~500 KB raw HTML per post; 139 posts = ~70 MB).
           Without this, Chrome approaches OOM around scroll 65 and freezes
           the entire process (CPU 90%, memory spike, terminal hang).

        Height is read from data-fw-height, which markPosts already set when
        it computed offsetHeight for the size filter — no extra layout reflow.
        minHeight is set so page total height stays constant and Facebook's
        lazy-loader keeps scrolling correctly.

        WHY innerHTML='' and NOT replaceWith/remove:
          replaceWith/remove mutates the feed container's childNodes list,
          which fires React's mutation observer on the container itself →
          React reconciliation cascade → Chrome main thread frozen for minutes.
          innerHTML='' only mutates the post element's own subtree (a child
          the container manages, not the container's childList), so React does
          not immediately reconcile the feed.
        """
        try:
            self._safe_evaluate(page, """() => {
                document.querySelectorAll('[data-fw-post]').forEach(el => {
                    el.removeAttribute('data-fw-post');
                    el.setAttribute('data-fw-seen', '1');
                    el.setAttribute('data-fw-placeholder', '1');
                    // Use cached height (set by markPosts) — avoids an extra
                    // offsetHeight call that would force a layout reflow here.
                    const h = parseInt(el.getAttribute('data-fw-height') || '300', 10);
                    el.innerHTML = '';
                    el.style.minHeight = h + 'px';
                });
            }""")
        except Exception:
            pass

    # ── Overlay handling ─────────────────────────────────────────────────────

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
