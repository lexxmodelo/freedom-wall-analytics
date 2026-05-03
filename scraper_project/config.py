"""
Configuration for the Freedom Wall scraper.

All institution identifiers are anonymized except SLU (the researchers' institution).
URLs contain page identifiers which are required for scraping but should not appear
in published outputs.
"""

from dataclasses import dataclass, field
from typing import Optional
import os

# ---------------------------------------------------------------------------
# Target pages
# ---------------------------------------------------------------------------

TARGETS = [
    {"code": "FW-01", "url": "https://www.facebook.com/ADMUFW/"},
    {"code": "FW-02", "url": "https://www.facebook.com/updilimanFW/"},
    {"code": "FW-03", "url": "https://www.facebook.com/FEUFW/"},
    {"code": "FW-04", "url": "https://www.facebook.com/uplbfreedomwall/"},
    {"code": "FW-05", "url": "https://www.facebook.com/LPUBFreedomWall"},
    {"code": "FW-06", "url": "https://www.facebook.com/CSUFW/"},
    {"code": "FW-07", "url": "https://www.facebook.com/p/UPB-Freedom-Wall-61574940063586/"},
    {"code": "FW-08", "url": "https://www.facebook.com/p/BSU-Freedom-Wall-61576546425176/"},
    {"code": "FW-09", "url": "https://www.facebook.com/TheUBFiles/"},
    {"code": "SLU",   "url": "https://www.facebook.com/p/SLU-Freedom-Wall-61563510362403/"},
]


@dataclass
class ScraperConfig:
    """Central configuration object passed to all components."""

    # --- Collection targets ---
    target_posts: int = 4000
    min_posts_threshold: int = 10

    # --- Timing / rate-limiting ---
    scroll_delay_min: float = 3.0
    scroll_delay_max: float = 7.0
    page_delay_min: float = 60.0
    page_delay_max: float = 120.0
    page_load_timeout: int = 30_000          # ms
    modal_wait_timeout: int = 3_000          # ms

    # --- Scrolling ---
    max_scroll_attempts: int = 200
    scroll_pixels: int = 900
    stale_scroll_limit: int = 15             # stop after N scrolls with no new posts
    max_modal_dismiss_attempts: int = 3

    # --- Per-page time cap ---
    page_timeout_seconds: int = 600          # raised to 28800 (8h) in auth mode

    # --- Freeze-proof architecture (network interception + periodic restart) ---
    network_intercept_mode: bool = True       # passive collector on /api/graphql/ responses
    # Empirically: hard freeze at ~scroll 600 even with low heap (CDP IPC stall,
    # not heap exhaustion). Restart at 500 leaves comfortable margin and lets
    # session 1 yield ~1400+ posts reliably before cursor-driven session 2.
    max_scrolls_per_session: int = 500
    session_restart_threshold: int = 500      # alias-style: restart trigger for clarity in logs
    memory_check_interval: int = 25           # CDP HeapProfiler.collectGarbage + heap log cadence
    heap_pressure_mb: int = 700               # backstop: restart early if heap_used exceeds this (MB)
    network_alive_window_secs: float = 12.0   # treat extractor as alive if a response arrived within this window

    # --- Authentication (cookie-based) ---
    cookie_file: Optional[str] = None        # path to cookies.json from extract_cookies.py
    authenticated: bool = False              # set automatically when cookies are loaded

    # --- Persistent browser profile (keeps session alive across multi-hour runs) ---
    use_persistent_context: bool = True
    persistent_profile_dir: str = ""         # filled at runtime from tempfile.gettempdir()

    # --- Checkpointing ---
    checkpoint_interval: int = 200           # flush collected posts to disk every N posts

    # --- Browser ---
    headless: bool = True
    browser_channel: Optional[str] = "chrome"  # use system Chrome (Playwright-bundled Chromium fails headed on Win11+Py3.14)

    # --- Headed debug mode (opt-in via --headed CLI flag) ---
    headed: bool = False                     # master flag; True forces headless=False + debug behaviors
    debug_screenshots: bool = False          # capture screenshots scrolls 35-70 every 5
    debug_screenshot_dir: str = os.path.join(os.path.dirname(__file__), "debug_screenshots")
    debug_evaluate_timeout_ms: int = 15_000  # reserved: Playwright Python evaluate() has no timeout kwarg
    js_heap_size_mb: int = 2048              # V8 --max_old_space_size (was hardcoded 512)
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    viewport_width: int = 1280
    viewport_height: int = 800
    block_media: bool = True                 # block images/video to save bandwidth

    # --- Retry ---
    max_retries: int = 3
    retry_backoff_base: float = 5.0          # seconds; multiplied by 2^attempt

    # --- Apify (alternative) ---
    apify_token: Optional[str] = None
    apify_cookie: str = ""

    # --- Semester windows (for adaptive collection) ---
    semester_windows: list = field(default_factory=lambda: [
        {"label": "AY2024-2025 2nd Sem", "start": "2025-01-01", "end": "2025-05-31"},
        {"label": "AY2024-2025 1st Sem", "start": "2024-06-01", "end": "2024-12-31"},
        {"label": "AY2023-2024 2nd Sem", "start": "2024-01-01", "end": "2024-05-31"},
        {"label": "AY2023-2024 1st Sem", "start": "2023-06-01", "end": "2023-12-31"},
    ])

    # --- Paths ---
    output_dir: str = os.path.join(os.path.dirname(__file__), "data")
    log_dir: str = os.path.join(os.path.dirname(__file__), "logs")

    # --- Strategies (ordered by preference) ---
    strategies: list = field(default_factory=lambda: [
        "desktop",     # www.facebook.com — full JS rendering
        "basic_mobile", # mbasic.facebook.com — minimal JS, simpler DOM
    ])

    scraper_version: str = "1.0.0"

    def get_target(self, code: str) -> Optional[dict]:
        """Look up a target by its anonymized code."""
        for t in TARGETS:
            if t["code"] == code:
                return t
        return None
