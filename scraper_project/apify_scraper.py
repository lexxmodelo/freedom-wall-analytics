"""
Apify-based Facebook Page Scraper integration.

Uses the Apify platform to collect posts from public Facebook pages.
Requires an Apify API token and (optionally) a Facebook session cookie.

Usage from main.py:
    python main.py --mode apify --apify-token YOUR_TOKEN

Or standalone:
    python apify_scraper.py --token YOUR_TOKEN --targets FW-01 SLU
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime

from config import ScraperConfig, TARGETS
from utils import setup_logger, deduplicate_posts, PHT

logger = logging.getLogger("fw_scraper")

try:
    from apify_client import ApifyClient
except ImportError:
    ApifyClient = None


# Known Apify actor IDs for Facebook page scraping (try in order)
ACTOR_IDS = [
    "apify/facebook-posts-scraper",
    "apify/facebook-pages-scraper",
]


class ApifyScraper:
    """Collect Facebook page posts via the Apify platform."""

    def __init__(self, config: ScraperConfig, apify_token: str, cookie_string: str = ""):
        if ApifyClient is None:
            raise ImportError(
                "apify-client is not installed. Run: pip install apify-client"
            )
        self.cfg = config
        self.client = ApifyClient(apify_token)
        self.cookie_string = cookie_string

    def scrape_target(self, target: dict) -> dict:
        """Scrape a single target page using Apify."""
        code = target["code"]
        url = target["url"]
        logger.info("[%s] Starting Apify scrape for %s", code, url)
        start = time.monotonic()

        run_input = {
            "startUrls": [{"url": url}],
            "maxPosts": self.cfg.target_posts,
            "maxPostDate": "2025-06-01",
            "minPostDate": "2023-06-01",
            "maxComments": 0,
            "maxReviews": 0,
        }

        if self.cookie_string:
            run_input["cookie"] = self.cookie_string

        posts = []
        status = "no_data"
        actor_used = "none"

        for actor_id in ACTOR_IDS:
            try:
                logger.info("[%s] Trying actor: %s", code, actor_id)
                run = self.client.actor(actor_id).call(
                    run_input=run_input,
                    timeout_secs=600,
                    memory_mbytes=1024,
                )
                dataset_id = run.get("defaultDatasetId")
                if not dataset_id:
                    logger.warning("[%s] No dataset returned from %s", code, actor_id)
                    continue

                items = list(self.client.dataset(dataset_id).iterate_items())
                logger.info("[%s] Actor %s returned %d items", code, actor_id, len(items))

                if items:
                    posts = [self._convert_item(item) for item in items if item]
                    posts = [p for p in posts if p and p.get("text")]
                    actor_used = actor_id
                    break

            except Exception as exc:
                logger.error("[%s] Actor %s failed: %s", code, actor_id, exc)
                continue

        posts = deduplicate_posts(posts)
        elapsed = time.monotonic() - start

        if posts:
            status = "target_reached" if len(posts) >= self.cfg.target_posts else "partial_collected"
        else:
            status = "no_data"

        logger.info(
            "[%s] Apify complete: %d posts via %s in %.0fs",
            code, len(posts), actor_used, elapsed,
        )

        return {
            "metadata": {
                "institution_code": code,
                "strategy_used": f"apify:{actor_used}",
                "total_posts_collected": len(posts),
                "target_posts": self.cfg.target_posts,
                "collection_status": status,
                "duration_seconds": round(elapsed, 1),
                "scraper_version": self.cfg.scraper_version,
                "scrape_timestamp": datetime.now(PHT).isoformat(),
            },
            "posts": posts,
        }

    @staticmethod
    def _convert_item(item: dict) -> dict:
        """Convert an Apify result item to our standard schema."""
        text = item.get("text") or item.get("message") or item.get("postText") or ""
        if not text.strip():
            return {}

        # Timestamp
        ts_raw = item.get("time") or item.get("timestamp") or item.get("date") or ""
        ts_iso = None
        if ts_raw:
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
                try:
                    from datetime import datetime as dt_
                    dt_obj = dt_.strptime(str(ts_raw), fmt)
                    dt_obj = dt_obj.replace(tzinfo=PHT)
                    ts_iso = dt_obj.isoformat()
                    break
                except ValueError:
                    continue
            if not ts_iso:
                ts_iso = str(ts_raw)

        # Engagement
        engagement = {
            "reactions": int(item.get("likes", 0) or item.get("reactions", 0) or 0),
            "comments": int(item.get("comments", 0) or 0),
            "shares": int(item.get("shares", 0) or 0),
        }

        # URL
        post_url = item.get("url") or item.get("postUrl") or item.get("link") or ""

        return {
            "text": text.strip(),
            "timestamp_iso": ts_iso,
            "timestamp_raw": str(ts_raw),
            "engagement": engagement,
            "post_url": post_url,
        }


# ── Standalone CLI ───────────────────────────────────────────────────────────

def main():
    if ApifyClient is None:
        print("ERROR: apify-client not installed. Run: pip install apify-client")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Apify-based Facebook scraper.")
    parser.add_argument("--token", required=True, help="Apify API token")
    parser.add_argument("--targets", nargs="*", default=None, help="Institution codes")
    parser.add_argument("--cookie", default="", help="Facebook session cookie string")
    parser.add_argument("--target-posts", type=int, default=4000)
    parser.add_argument("--output-dir", default="data")
    args = parser.parse_args()

    config = ScraperConfig()
    config.target_posts = args.target_posts
    config.output_dir = args.output_dir

    log = setup_logger(log_dir=config.log_dir)
    log.info("Apify scraper starting")

    os.makedirs(config.output_dir, exist_ok=True)

    targets = TARGETS
    if args.targets:
        targets = [t for t in TARGETS if t["code"] in args.targets]

    scraper = ApifyScraper(config, args.token, args.cookie)

    for i, target in enumerate(targets):
        log.info("Processing %d/%d: %s", i + 1, len(targets), target["code"])
        result = scraper.scrape_target(target)

        out_path = os.path.join(config.output_dir, f"{target['code']}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        log.info("Saved %s", out_path)

    log.info("Done")


if __name__ == "__main__":
    main()
