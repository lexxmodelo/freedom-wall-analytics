"""
Diagnostic: examine ALL links and structure inside an actual FW post.
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

        # Find a post container and examine its contents in detail
        result = page.evaluate("""() => {
            // Find the #SLUFreedomWall text node (skip script tags)
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                { acceptNode: n => {
                    if (n.parentElement && n.parentElement.tagName === 'SCRIPT') return NodeFilter.FILTER_REJECT;
                    return n.textContent.includes('#SLUFreedomWall') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
                }}
            );
            const node = walker.nextNode();
            if (!node) return {error: "No FW text found"};

            // Walk up to find the post container (child of feed container)
            let el = node.parentElement;
            let postContainer = null;
            while (el && el !== document.body) {
                const parent = el.parentElement;
                if (parent && parent.children.length >= 8) {
                    postContainer = el;
                    break;
                }
                el = parent;
            }

            if (!postContainer) return {error: "No post container found"};

            // Examine the post container
            const text = postContainer.innerText;
            const links = Array.from(postContainer.querySelectorAll('a[href]')).map(a => ({
                href: a.getAttribute('href').substring(0, 200),
                text: a.innerText.substring(0, 50),
                ariaLabel: (a.getAttribute('aria-label') || '').substring(0, 100),
                role: a.getAttribute('role') || '',
            }));

            // Find all elements with aria-label in the post
            const ariaElements = Array.from(postContainer.querySelectorAll('[aria-label]'))
                .filter(el => el.tagName !== 'A')
                .map(el => ({
                    tag: el.tagName,
                    ariaLabel: el.getAttribute('aria-label').substring(0, 100),
                    role: el.getAttribute('role') || '',
                }));

            // Get the full inner HTML structure (abbreviated)
            const outerHTML = postContainer.outerHTML.substring(0, 500);

            return {
                text: text.substring(0, 300),
                textLen: text.length,
                linkCount: links.length,
                links: links.slice(0, 15),
                ariaElements: ariaElements.slice(0, 10),
                htmlPreview: outerHTML,
                width: Math.round(postContainer.getBoundingClientRect().width),
                height: Math.round(postContainer.getBoundingClientRect().height),
            };
        }""")

        if "error" in result:
            print(f"ERROR: {result['error']}")
        else:
            safe_text = result['text'][:200].encode('ascii', 'replace').decode()
            print(f"Post container: {result['width']}x{result['height']}, textLen={result['textLen']}")
            print(f"Text: {safe_text}")
            print(f"\nLinks ({result['linkCount']} total):")
            for i, link in enumerate(result['links']):
                safe_href = link['href'][:120]
                safe_label = link['ariaLabel'][:60] if link['ariaLabel'] else ''
                print(f"  [{i}] href={safe_href}")
                print(f"       text={link['text']!r} label={safe_label!r} role={link['role']!r}")
            print(f"\nAria elements:")
            for el in result['ariaElements']:
                print(f"  {el['tag']} role={el['role']!r} label={el['ariaLabel']!r}")

        browser.close()

if __name__ == "__main__":
    main()
