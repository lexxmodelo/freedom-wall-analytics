"""
Diagnostic script: inspect DOM structure of Facebook page in authenticated mode.
Dumps info about all [role='article'] elements to understand comment vs post nesting.
"""

import json
import os
from playwright.sync_api import sync_playwright

def main():
    cookies_path = "cookies.json"
    with open(cookies_path, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    url = "https://www.facebook.com/p/SLU-Freedom-Wall-61563510362403/"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="en-US",
        )
        context.add_cookies(cookies)
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        # Click Posts tab
        try:
            el = page.locator("span:has-text('Posts')").first
            if el.is_visible(timeout=3000):
                el.click()
                print("Clicked Posts tab")
                page.wait_for_timeout(3000)
        except Exception:
            print("Posts tab not found")

        # Dismiss overlays
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        # Scroll a few times to load content
        for i in range(5):
            page.evaluate("window.scrollBy(0, 1200)")
            page.wait_for_timeout(2000)

        # Now inspect all articles
        articles = page.query_selector_all("[role='article']")
        print(f"\nTotal [role='article'] elements: {len(articles)}")
        print("=" * 80)

        for i, article in enumerate(articles[:30]):
            try:
                info = article.evaluate("""el => {
                    const hasParentArticle = !!el.parentElement.closest('[role="article"]');
                    const text = el.innerText.substring(0, 200);
                    const links = el.querySelectorAll('a[href]');
                    let postUrl = null;
                    let commentId = false;
                    for (const a of links) {
                        const href = a.getAttribute('href') || '';
                        if (href.includes('permalink') || href.includes('/posts/') || href.includes('story_fbid')) {
                            postUrl = href.substring(0, 200);
                            if (href.includes('comment_id=')) commentId = true;
                            break;
                        }
                    }

                    // Check aria-label on the article itself
                    const ariaLabel = el.getAttribute('aria-label') || '';

                    // Check parent classes/attributes
                    const parentTag = el.parentElement ? el.parentElement.tagName : 'none';
                    const parentRole = el.parentElement ? (el.parentElement.getAttribute('role') || '') : '';

                    // Get rect for position info
                    const rect = el.getBoundingClientRect();

                    return {
                        hasParentArticle,
                        textPreview: text.replace(/\\n/g, ' | ').substring(0, 150),
                        postUrl: postUrl,
                        hasCommentId: commentId,
                        ariaLabel: ariaLabel.substring(0, 100),
                        parentTag,
                        parentRole,
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                    };
                }""")

                nested = "NESTED" if info["hasParentArticle"] else "TOP"
                comment = "COMMENT_URL" if info["hasCommentId"] else ""
                messenger = "MESSENGER" if "Message sent" in info["textPreview"] or "encryption" in info["textPreview"] else ""
                tag = "FW_TAG" if "#SLUFreedomWall" in info["textPreview"] else ""

                flags = " ".join(f for f in [nested, comment, messenger, tag] if f)

                print(f"\n[{i}] {flags}")
                print(f"  aria-label: {info['ariaLabel']!r}")
                print(f"  parent: {info['parentTag']} role={info['parentRole']!r}")
                print(f"  rect: x={info['x']} y={info['y']} w={info['width']} h={info['height']}")
                print(f"  url: {info['postUrl']}")
                print(f"  text: {info['textPreview'][:120]}")
            except Exception as e:
                print(f"\n[{i}] ERROR: {e}")

        browser.close()

if __name__ == "__main__":
    main()
