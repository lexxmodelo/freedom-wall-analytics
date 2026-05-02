"""
Diagnostic: find what DOM element contains actual Freedom Wall posts.
"""

import json
from playwright.sync_api import sync_playwright

def main():
    with open("cookies.json", "r", encoding="utf-8") as f:
        cookies = json.load(f)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False, channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36",
            locale="en-US",
        )
        context.add_cookies(cookies)
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page.goto("https://www.facebook.com/p/SLU-Freedom-Wall-61563510362403/", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        try:
            el = page.locator("span:has-text('Posts')").first
            if el.is_visible(timeout=3000):
                el.click()
                page.wait_for_timeout(3000)
        except Exception:
            pass

        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        for i in range(3):
            page.evaluate("window.scrollBy(0, 1200)")
            page.wait_for_timeout(2000)

        # Strategy 1: Search for elements containing #SLUFreedomWall text
        print("=== SEARCHING FOR #SLUFreedomWall TEXT ===")
        results = page.evaluate("""() => {
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                { acceptNode: n => n.textContent.includes('#SLUFreedomWall') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT }
            );
            const found = [];
            let node;
            while ((node = walker.nextNode()) && found.length < 5) {
                let el = node.parentElement;
                const path = [];
                for (let i = 0; i < 8 && el; i++) {
                    const role = el.getAttribute('role') || '';
                    const cls = el.className ? (typeof el.className === 'string' ? el.className.substring(0, 30) : '') : '';
                    const tag = el.tagName;
                    path.push(`${tag}[role=${role}][class=${cls}]`);
                    el = el.parentElement;
                }
                found.push({
                    text: node.textContent.substring(0, 100),
                    path: path,
                });
            }
            return found;
        }""")

        for i, r in enumerate(results):
            print(f"\n[{i}] text: {r['text'][:80]}")
            print(f"  DOM path (child -> parent):")
            for j, p in enumerate(r["path"]):
                print(f"    {'  ' * j}{p}")

        # Strategy 2: Look at the feed container structure
        print("\n\n=== FEED CONTAINER STRUCTURE ===")
        feed_info = page.evaluate("""() => {
            // Look for common Facebook feed containers
            const selectors = [
                '[role="feed"]',
                '[role="main"]',
                '[data-pagelet="ProfileTimeline"]',
                '[data-pagelet*="Feed"]',
                '[data-pagelet*="Timeline"]',
            ];
            const results = [];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const children = Array.from(el.children).slice(0, 10).map(c => {
                        const role = c.getAttribute('role') || '';
                        const tag = c.tagName;
                        const text = c.innerText ? c.innerText.substring(0, 80).replace(/\\n/g, ' | ') : '';
                        const hasFW = c.innerText ? c.innerText.includes('#SLUFreedomWall') : false;
                        return {tag, role, text, hasFW, childCount: c.children.length};
                    });
                    results.push({selector: sel, childCount: el.children.length, children});
                }
            }
            return results;
        }""")

        for r in feed_info:
            print(f"\nSelector: {r['selector']} — {r['childCount']} children")
            for j, c in enumerate(r["children"]):
                fw = " [HAS_FW]" if c["hasFW"] else ""
                print(f"  [{j}] {c['tag']} role={c['role']!r} children={c['childCount']}{fw}")
                if c["text"]:
                    safe = c["text"][:80].encode("ascii", "replace").decode()
                    print(f"       text: {safe}")

        # Strategy 3: What does the actual post div look like?
        print("\n\n=== POST CONTAINER ANALYSIS ===")
        post_info = page.evaluate("""() => {
            // Find any element containing #SLUFreedomWall and walk up to find the post container
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                { acceptNode: n => n.textContent.includes('#SLUFreedomWall') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT }
            );
            const node = walker.nextNode();
            if (!node) return null;

            let el = node.parentElement;
            const ancestors = [];
            while (el && el !== document.body) {
                const role = el.getAttribute('role') || '';
                const tag = el.tagName;
                const cls = el.className ? (typeof el.className === 'string' ? el.className.substring(0, 50) : '') : '';
                const dataPagelet = el.getAttribute('data-pagelet') || '';
                const rect = el.getBoundingClientRect();
                ancestors.push({
                    tag, role, cls, dataPagelet,
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    childCount: el.children.length,
                    hasArticleRole: role === 'article',
                });
                el = el.parentElement;
            }
            return ancestors;
        }""")

        if post_info:
            print("Ancestors of #SLUFreedomWall text (inner -> outer):")
            for j, a in enumerate(post_info):
                print(f"  [{j}] {a['tag']} role={a['role']!r} class={a['cls']!r} pagelet={a['dataPagelet']!r} "
                      f"w={a['width']} h={a['height']} children={a['childCount']}")
        else:
            print("No #SLUFreedomWall text found on page!")

        browser.close()

if __name__ == "__main__":
    main()
