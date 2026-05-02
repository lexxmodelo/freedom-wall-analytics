"""
Interactive Facebook login -> cookie export.

Opens a browser window. The user logs into Facebook manually.
After login, cookies are saved to cookies.json for the scraper to use.

Usage:
    python extract_cookies.py
    python extract_cookies.py --output my_cookies.json
"""

import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright


def extract(output_path: str):
    import tempfile
    user_data_dir = os.path.join(tempfile.gettempdir(), "fb_login_profile")
    os.makedirs(user_data_dir, exist_ok=True)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            channel="chrome",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")

        print()
        print("=" * 55)
        print("  A browser window has opened.")
        print("  Please log in to your Facebook account.")
        print()
        print("  IMPORTANT:")
        print("   - Use a research / secondary account if possible")
        print("   - Only public page content will be accessed")
        print("   - Your credentials are NOT stored by this tool")
        print("=" * 55)
        print()

        print("  1. Enter your credentials")
        print("  2. Complete any CAPTCHA or 2FA prompts")
        print("  3. Wait until you see the Facebook News Feed")
        print()
        print("  The script will auto-detect when login is complete.")
        print("  (Checking for session cookies every 5 seconds, up to 10 minutes)")
        print()

        max_checks = 120
        for check in range(max_checks):
            page.wait_for_timeout(5000)
            cookies = context.cookies()
            cookie_names = {c["name"] for c in cookies if "facebook.com" in c.get("domain", "")}
            if "c_user" in cookie_names and "xs" in cookie_names:
                print(f"  Session cookies detected after {(check + 1) * 5}s!")
                break
            if (check + 1) % 6 == 0:
                print(f"  Still waiting... ({(check + 1) * 5}s elapsed, found: {', '.join(sorted(cookie_names))})")
        else:
            print("  Timed out after 10 minutes.")

        page.wait_for_timeout(3000)

        all_cookies = context.cookies()
        fb_cookies = [c for c in all_cookies if "facebook.com" in c.get("domain", "")]

        cookie_names = {c["name"] for c in fb_cookies}
        has_session = "c_user" in cookie_names and "xs" in cookie_names

        if not has_session:
            print()
            print("Session cookies not found yet. Waiting 15 more seconds...")
            page.wait_for_timeout(15_000)

            all_cookies = context.cookies()
            fb_cookies = [c for c in all_cookies if "facebook.com" in c.get("domain", "")]
            cookie_names = {c["name"] for c in fb_cookies}
            has_session = "c_user" in cookie_names and "xs" in cookie_names

        if not has_session:
            print()
            print("WARNING: Session cookies (c_user, xs) still not found.")
            print(f"Found {len(fb_cookies)} cookies: " + ", ".join(sorted(cookie_names)))
            print()
            all_names = {c["name"] for c in all_cookies}
            if all_names - cookie_names:
                print(f"Non-FB cookies: " + ", ".join(sorted(all_names - cookie_names)))
            print()
            print("Saving what we have. The scraper may have limited access.")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(fb_cookies, f, indent=2)

        # --- Save localStorage (Facebook stores session tokens here, not just in cookies) ---
        # Without localStorage, a fallback cookie-only session stalls after ~80-100 posts
        # because Facebook's infinite scroll API relies on tokens stored in localStorage.
        state_path = os.path.splitext(output_path)[0] + "_state.json"
        try:
            local_storage = page.evaluate("""() => {
                const result = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    try { result[key] = localStorage.getItem(key); } catch(e) {}
                }
                return result;
            }""")
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump({"localStorage": local_storage}, f, indent=2)
            print(f"  Saved {len(local_storage)} localStorage keys to {state_path}")
        except Exception as _ls_err:
            print(f"  Note: Could not save localStorage state ({_ls_err}) — continuing without it.")

        print()
        if has_session:
            print(f"Saved {len(fb_cookies)} Facebook cookies to {output_path}")
            print("  Session cookies (c_user, xs) PRESENT -- full auth enabled!")
        else:
            print(f"Saved {len(fb_cookies)} Facebook cookies to {output_path}")
            print("  WARNING: No session cookies -- scraping will be limited.")
        print()
        print(f"To scrape with these cookies:")
        print(f"  python main.py --cookies {output_path}")
        print()

        context.close()


def main():
    parser = argparse.ArgumentParser(description="Extract Facebook session cookies.")
    parser.add_argument(
        "--output", "-o",
        default="cookies.json",
        help="Output file for cookies (default: cookies.json)",
    )
    args = parser.parse_args()
    extract(args.output)


if __name__ == "__main__":
    main()
