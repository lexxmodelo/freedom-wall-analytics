"""
Diagnostic: trace full ancestor chain from FW post text to find post boundaries.
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

        # Find the full ancestor chain for each FW post
        result = page.evaluate("""() => {
            // Find all text nodes containing #SLUFreedomWall
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                { acceptNode: n => {
                    // Skip script tags
                    if (n.parentElement && n.parentElement.tagName === 'SCRIPT') return NodeFilter.FILTER_REJECT;
                    return n.textContent.includes('#SLUFreedomWall') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
                }}
            );

            const posts = [];
            let node;
            while ((node = walker.nextNode()) && posts.length < 3) {
                let el = node.parentElement;

                // Walk up to find the post boundary - look for a container that
                // has siblings (other posts at the same level)
                const ancestors = [];
                while (el && el !== document.body) {
                    const role = el.getAttribute('role') || '';
                    const tag = el.tagName;
                    const siblingCount = el.parentElement ? el.parentElement.children.length : 0;
                    const rect = el.getBoundingClientRect();
                    const hasPermalink = !!el.querySelector('a[href*="permalink"], a[href*="/posts/"]');
                    const innerTextLen = el.innerText ? el.innerText.length : 0;

                    ancestors.push({
                        tag, role,
                        siblingCount,
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                        hasPermalink,
                        innerTextLen,
                        depth: ancestors.length,
                    });
                    el = el.parentElement;
                }

                // Get the FW tag number
                const match = node.textContent.match(/#SLUFreedomWall(\\d+)/);
                const fwNum = match ? match[1] : '?';

                posts.push({fwNum, ancestors});
            }
            return posts;
        }""")

        for p in result:
            print(f"\n=== #SLUFreedomWall{p['fwNum']} ===")
            print("Ancestor chain (inner -> outer):")
            for a in p["ancestors"]:
                indent = "  " * (a["depth"] + 1)
                has_pl = " [PERMALINK]" if a["hasPermalink"] else ""
                print(f"{indent}{a['tag']} role={a['role']!r} siblings={a['siblingCount']} "
                      f"w={a['width']} h={a['height']} textLen={a['innerTextLen']}{has_pl}")

        # Also find the common "feed" container where posts are siblings
        print("\n\n=== FINDING FEED CONTAINER ===")
        feed = page.evaluate("""() => {
            // Find TWO different FW posts and trace to their common ancestor
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                { acceptNode: n => {
                    if (n.parentElement && n.parentElement.tagName === 'SCRIPT') return NodeFilter.FILTER_REJECT;
                    return n.textContent.includes('#SLUFreedomWall') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
                }}
            );

            const nodes = [];
            let n;
            while ((n = walker.nextNode()) && nodes.length < 2) {
                // Only keep unique post numbers
                const m = n.textContent.match(/#SLUFreedomWall(\\d+)/);
                if (m && !nodes.find(x => x.num === m[1])) {
                    nodes.push({num: m[1], el: n.parentElement});
                }
            }

            if (nodes.length < 2) return {error: "Less than 2 FW posts found"};

            // Walk up from each to find common ancestor
            const getAncestors = (el) => {
                const list = [];
                while (el) { list.push(el); el = el.parentElement; }
                return list;
            };

            const ancestors1 = getAncestors(nodes[0].el);
            const ancestors2 = getAncestors(nodes[1].el);
            const set2 = new Set(ancestors2);

            let commonAncestor = null;
            for (const a of ancestors1) {
                if (set2.has(a)) { commonAncestor = a; break; }
            }

            if (!commonAncestor) return {error: "No common ancestor"};

            // The post containers are the direct children of the common ancestor
            // that contain FW text
            const children = Array.from(commonAncestor.children);
            const postContainers = children.map((c, i) => {
                const hasFW = c.innerText && c.innerText.includes('#SLUFreedomWall');
                const match = hasFW ? c.innerText.match(/#SLUFreedomWall(\\d+)/) : null;
                const rect = c.getBoundingClientRect();
                const tag = c.tagName;
                const role = c.getAttribute('role') || '';

                // Try to find permalink
                const pl = c.querySelector('a[href*="permalink"], a[href*="/posts/"], a[href*="story_fbid"]');
                const plHref = pl ? pl.getAttribute('href').substring(0, 100) : null;

                return {
                    index: i, tag, role,
                    hasFW,
                    fwNum: match ? match[1] : null,
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    textLen: c.innerText ? c.innerText.length : 0,
                    permalink: plHref,
                };
            });

            return {
                commonAncestor: {
                    tag: commonAncestor.tagName,
                    role: commonAncestor.getAttribute('role') || '',
                    childCount: children.length,
                },
                posts: postContainers.filter(p => p.height > 0),
            };
        }""")

        if "error" in feed:
            print(f"ERROR: {feed['error']}")
        else:
            ca = feed["commonAncestor"]
            print(f"Common ancestor: {ca['tag']} role={ca['role']!r} — {ca['childCount']} children")
            print(f"\nChildren with content:")
            for p in feed["posts"]:
                fw = f" FW#{p['fwNum']}" if p["hasFW"] else ""
                pl = f" url={p['permalink']}" if p["permalink"] else ""
                print(f"  [{p['index']}] {p['tag']} role={p['role']!r} "
                      f"w={p['width']} h={p['height']} textLen={p['textLen']}{fw}{pl}")

        browser.close()

if __name__ == "__main__":
    main()
