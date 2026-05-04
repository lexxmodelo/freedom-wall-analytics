"""
Freedom Wall Scraper — Entry Point

Usage:
    # Step 1: Extract cookies (one-time, opens browser for login)
    python extract_cookies.py

    # Step 2: Scrape with authentication (gets semester-scale data)
    python main.py --cookies cookies.json
    python main.py --cookies cookies.json --targets SLU --headed
    python main.py --cookies cookies.json --semester-filter

    # Without auth (limited data — see scraping_strategy.md)
    python main.py --targets SLU

    # Apify mode (requires paid account)
    python main.py --mode apify --apify-token YOUR_TOKEN
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

from config import ScraperConfig, TARGETS
from scraper import FacebookScraper
from utils import setup_logger, random_sleep, PHT, is_within_window


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape publicly accessible Facebook Freedom Wall pages.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python extract_cookies.py              # one-time login\n"
            "  python main.py --cookies cookies.json   # full semester scrape\n"
            "  python main.py --targets SLU --headed    # debug single page\n"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["playwright", "apify"],
        default="playwright",
        help="Scraping mode: 'playwright' (default) or 'apify'.",
    )
    parser.add_argument(
        "--cookies",
        default=None,
        help="Path to cookies.json (from extract_cookies.py). Enables full-depth scraping.",
    )
    parser.add_argument(
        "--targets",
        nargs="*",
        default=None,
        help="Institution codes to scrape (e.g., FW-01 SLU). Default: all.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode (visible) for debugging.",
    )
    parser.add_argument(
        "--target-posts",
        type=int,
        default=4000,
        help="Target number of posts per page (default: 4000).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: ./data).",
    )
    parser.add_argument(
        "--semester-filter",
        action="store_true",
        help="After scraping, filter posts to the latest semester window only.",
    )
    parser.add_argument(
        "--apify-token",
        default=None,
        help="Apify API token (required for --mode apify).",
    )
    parser.add_argument(
        "--apify-cookie",
        default="",
        help="Facebook cookie string for Apify actor (optional).",
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=None,
        help=(
            "Override the strategy chain (default order: "
            "desktop_graphql_httpx, desktop, basic_mobile_httpx, basic_mobile). "
            "Useful for testing a single strategy in isolation, e.g.: "
            "--strategies desktop_graphql_httpx OR --strategies desktop"
        ),
    )
    return parser.parse_args()


def run_playwright(args, config, targets, logger):
    """Run the Playwright-based scraper."""
    scraper = FacebookScraper(config)
    all_results: list[dict] = []
    overall_start = time.monotonic()

    for i, target in enumerate(targets):
        code = target["code"]
        logger.info("=" * 50)
        logger.info("Processing %d/%d: %s", i + 1, len(targets), code)

        result = scraper.scrape_target(target)

        if args.semester_filter and config.semester_windows:
            window = config.semester_windows[0]
            before = len(result["posts"])
            result["posts"] = [
                p for p in result["posts"]
                if is_within_window(p.get("timestamp_iso"), window["start"], window["end"])
            ]
            after = len(result["posts"])
            result["metadata"]["semester_filter"] = window["label"]
            result["metadata"]["posts_before_filter"] = before
            result["metadata"]["total_posts_collected"] = after
            logger.info("[%s] Semester filter (%s): %d -> %d posts", code, window["label"], before, after)

        result["metadata"]["scrape_timestamp"] = datetime.now(PHT).isoformat()
        result["metadata"]["authenticated"] = config.authenticated

        out_path = os.path.join(config.output_dir, f"{code}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info("[%s] Saved to %s (%d posts)", code, out_path, result["metadata"]["total_posts_collected"])

        all_results.append(result)

        if i < len(targets) - 1:
            logger.info("Waiting between pages...")
            random_sleep(config.page_delay_min, config.page_delay_max)

    return all_results, time.monotonic() - overall_start


def run_apify(args, config, targets, logger):
    """Run the Apify-based scraper."""
    from apify_scraper import ApifyScraper

    if not args.apify_token:
        logger.error("--apify-token is required for apify mode")
        sys.exit(1)

    scraper = ApifyScraper(config, args.apify_token, args.apify_cookie)
    all_results: list[dict] = []
    overall_start = time.monotonic()

    for i, target in enumerate(targets):
        code = target["code"]
        logger.info("Processing %d/%d: %s", i + 1, len(targets), code)

        result = scraper.scrape_target(target)

        out_path = os.path.join(config.output_dir, f"{code}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info("[%s] Saved to %s (%d posts)", code, out_path, result["metadata"]["total_posts_collected"])

        all_results.append(result)

    return all_results, time.monotonic() - overall_start


def print_summary(all_results, elapsed, config, logger):
    """Generate and print the summary."""
    summary = {
        "scrape_timestamp": datetime.now(PHT).isoformat(),
        "scraper_version": config.scraper_version,
        "authenticated": config.authenticated,
        "total_pages_attempted": len(all_results),
        "total_pages_with_data": sum(
            1 for r in all_results if r["metadata"]["total_posts_collected"] > 0
        ),
        "total_posts_collected": sum(
            r["metadata"]["total_posts_collected"] for r in all_results
        ),
        "duration_seconds": round(elapsed, 1),
        "pages": [
            {
                "code": r["metadata"]["institution_code"],
                "posts": r["metadata"]["total_posts_collected"],
                "status": r["metadata"]["collection_status"],
                "strategy": r["metadata"]["strategy_used"],
            }
            for r in all_results
        ],
    }

    summary_path = os.path.join(config.output_dir, "scrape_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("=" * 70)
    logger.info("SCRAPE COMPLETE")
    logger.info("  Mode: %s | Authenticated: %s", "playwright", config.authenticated)
    logger.info("  Pages: %d attempted, %d with data",
                summary["total_pages_attempted"], summary["total_pages_with_data"])
    logger.info("  Total posts: %d", summary["total_posts_collected"])
    logger.info("  Duration: %.0fs (%.1f min)", elapsed, elapsed / 60)
    logger.info("  Summary: %s", summary_path)
    logger.info("=" * 70)

    print()
    print("+--------+-------+---------------------+----------+")
    print("| Code   | Posts | Status              | Strategy |")
    print("+--------+-------+---------------------+----------+")
    for p in summary["pages"]:
        print(f"| {p['code']:<6} | {p['posts']:>5} | {p['status']:<19} | {p['strategy']:<8} |")
    print("+--------+-------+---------------------+----------+")
    print(f"\nTotal: {summary['total_posts_collected']} posts in {elapsed:.0f}s ({elapsed/60:.1f} min)")

    if not config.authenticated and summary["total_posts_collected"] < 500:
        print()
        print("TIP: Post count is low. For semester-scale data, use cookie auth:")
        print("  1. python extract_cookies.py")
        print("  2. python main.py --cookies cookies.json")


def main():
    args = parse_args()

    config = ScraperConfig()
    if args.cookies:
        config.cookie_file = args.cookies
    if args.headed:
        config.headed = True
        config.headless = False
        config.debug_screenshots = True
    if args.target_posts:
        config.target_posts = args.target_posts
    if args.output_dir:
        config.output_dir = args.output_dir
    if args.apify_token:
        config.apify_token = args.apify_token
    if args.strategies:
        config.strategies = list(args.strategies)

    logger = setup_logger(log_dir=config.log_dir)
    logger.info("=" * 70)
    logger.info("Freedom Wall Scraper v%s", config.scraper_version)
    logger.info("Mode: %s | Cookies: %s", args.mode, args.cookies or "none")
    logger.info("=" * 70)

    if args.targets:
        targets = [t for t in TARGETS if t["code"] in args.targets]
        missing = set(args.targets) - {t["code"] for t in targets}
        if missing:
            logger.error("Unknown target codes: %s", missing)
            sys.exit(1)
    else:
        targets = TARGETS

    logger.info("Targets: %s", [t["code"] for t in targets])
    logger.info("Target posts per page: %d", config.target_posts)

    os.makedirs(config.output_dir, exist_ok=True)

    if args.mode == "apify":
        all_results, elapsed = run_apify(args, config, targets, logger)
    else:
        all_results, elapsed = run_playwright(args, config, targets, logger)

    print_summary(all_results, elapsed, config, logger)


if __name__ == "__main__":
    main()
