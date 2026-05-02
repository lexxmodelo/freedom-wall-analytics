"""
Content extraction from Facebook DOM elements and raw HTML.

Three parser implementations:
  - DesktopHTMLParser  — BeautifulSoup from outerHTML snapshot (zero CDP calls, zero reflow)
  - DesktopParser      — sync methods for Playwright ElementHandle (www.facebook.com)
  - BasicMobileParser  — BeautifulSoup tags from mbasic.facebook.com HTML
"""

import re
import logging
from typing import Optional
from bs4 import BeautifulSoup

from utils import normalize_timestamp, post_hash

logger = logging.getLogger("fw_scraper")

_NOISE_PATTERNS = [
    re.compile(r"^(Like|Comment|Share|Send|React)$", re.I),
    re.compile(r"^\d+\s*(likes?|comments?|shares?|reactions?)$", re.I),
    re.compile(r"^(Write a comment|Press enter to post).*", re.I),
    re.compile(r"^(See more|See less|See translation)$", re.I),
    re.compile(r"^(Photo|Video|Live Video|Reel)$", re.I),
    re.compile(r"^Log\s*In", re.I),
    re.compile(r"^Sign\s*Up", re.I),
    re.compile(r"^(Create new account|Forgotten password)", re.I),
    re.compile(r"^All reactions:", re.I),
]

_ENGAGEMENT_PATTERN = re.compile(
    r"([\d,.]+[KkMm]?)\s*(reactions?|likes?|comments?|shares?)",
    re.I,
)


def _is_noise(line: str) -> bool:
    line = line.strip()
    if not line:
        return True
    return any(p.search(line) for p in _NOISE_PATTERNS)


def _parse_count(raw: str) -> int:
    raw = raw.strip().replace(",", "")
    multiplier = 1
    if raw.upper().endswith("K"):
        multiplier = 1_000
        raw = raw[:-1]
    elif raw.upper().endswith("M"):
        multiplier = 1_000_000
        raw = raw[:-1]
    try:
        return int(float(raw) * multiplier)
    except (ValueError, TypeError):
        return 0


def _extract_text_from_lines(raw: str) -> Optional[str]:
    """Filter noise and return the longest contiguous text block."""
    lines = raw.split("\n")
    clean = [ln.strip() for ln in lines if not _is_noise(ln)]
    blocks: list[str] = []
    current: list[str] = []
    for ln in clean:
        if ln:
            current.append(ln)
        else:
            if current:
                blocks.append("\n".join(current))
                current = []
    if current:
        blocks.append("\n".join(current))
    if not blocks:
        return None
    best = max(blocks, key=len)
    return best if len(best) > 5 else None


# ═══════════════════════════════════════════════════════════════════════════════
# Desktop HTML parser — BeautifulSoup from outerHTML snapshot (zero CDP calls)
# ═══════════════════════════════════════════════════════════════════════════════

class DesktopHTMLParser:
    """Parse Facebook posts from a raw HTML snapshot.

    Accepts the concatenated outerHTML of [data-fw-post] elements returned by a
    single page.evaluate() call.  All extraction is pure BS4 — no live DOM
    queries, no layout reflow, React untouched.
    """

    @staticmethod
    def parse_feed_html(html: str, seen_hashes: set) -> list[dict]:
        """Return new posts from a feed HTML snapshot, updating seen_hashes in place.

        Relies on data-fw-post attributes set by _find_post_elements (which
        identifies post containers via JS structure analysis).  Falls back to
        standard HTML selectors for unauthenticated pages.
        """
        soup = BeautifulSoup(html, "html.parser")

        # Primary: elements marked by _find_post_elements
        articles = soup.find_all(attrs={"data-fw-post": True})
        # Fallback 1: unauthenticated feed uses role="article"
        if not articles:
            articles = soup.find_all(attrs={"role": "article"})
        # Fallback 2: data-pagelet FeedUnit divs
        if not articles:
            articles = soup.find_all("div", attrs={"data-pagelet": re.compile(r"FeedUnit")})

        posts = []
        for article in articles:
            post = DesktopHTMLParser._parse_article(article)
            if not post or not post.get("text"):
                continue
            h = post_hash(post["text"])
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            post["post_id"] = h[:16]
            posts.append(post)

        return posts

    @staticmethod
    def _parse_article(article) -> Optional[dict]:
        text = DesktopHTMLParser._extract_text(article)
        if not text:
            return None
        ts_iso, ts_raw = DesktopHTMLParser._extract_timestamp(article, text)
        engagement = DesktopHTMLParser._extract_engagement(article)
        url = DesktopHTMLParser._extract_url(article)
        return {
            "text": text,
            "timestamp_iso": ts_iso,
            "timestamp_raw": ts_raw,
            "engagement": engagement,
            "post_url": url,
        }

    @staticmethod
    def _extract_text(article) -> Optional[str]:
        for attr, val in (
            ("data-ad-comet-preview", "message"),
            ("data-ad-preview", "message"),
        ):
            msg = article.find(attrs={attr: val})
            if msg:
                text = msg.get_text(separator="\n", strip=True)
                if text and len(text) > 5:
                    return text
        raw = article.get_text(separator="\n", strip=True)
        return _extract_text_from_lines(raw)

    @staticmethod
    def _extract_timestamp(article, text: str) -> tuple[Optional[str], Optional[str]]:
        time_el = article.find("time", attrs={"datetime": True})
        if time_el:
            return time_el.get("datetime"), time_el.get_text(strip=True)

        abbr = article.find("abbr", attrs={"data-utime": True})
        if abbr:
            from datetime import datetime as dt_, timezone as tz_
            utime = abbr.get("data-utime")
            ts_raw = abbr.get_text(strip=True)
            try:
                return dt_.fromtimestamp(int(utime), tz=tz_.utc).isoformat(), ts_raw
            except (ValueError, OSError):
                pass

        date_keywords = (
            "ago", "yesterday", "today",
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        )
        for sel in (
            "a[href*='/posts/'] span",
            "a[href*='story_fbid'] span",
            "a[href*='pfbid'] span",
            "a[href*='permalink'] span",
            "a[href*='/posts/']",
            "a[href*='story_fbid']",
            "a[href*='pfbid']",
        ):
            el = article.select_one(sel)
            if el:
                raw = el.get_text(strip=True)
                if raw and len(raw) < 50 and any(kw in raw.lower() for kw in date_keywords):
                    return normalize_timestamp(raw), raw

        for a in article.find_all("a", attrs={"aria-label": True}):
            label = a.get("aria-label", "")
            if any(kw in label.lower() for kw in date_keywords):
                return normalize_timestamp(label), label

        m = re.search(
            r"Submitted:\s+"
            r"((?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+\d{1,2},\s+\d{4}"
            r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)?)",
            text,
            re.I,
        )
        if m:
            raw = m.group(1).strip()
            return normalize_timestamp(raw), raw

        return None, None

    @staticmethod
    def _extract_engagement(article) -> dict:
        result = {"reactions": 0, "comments": 0, "shares": 0}
        for el in article.find_all(attrs={"aria-label": True}):
            label = el.get("aria-label", "")
            if not label:
                continue
            ll = label.lower()
            for key in ("reaction", "like"):
                if key in ll:
                    m = re.search(r"([\d,.]+[KkMm]?)", label)
                    if m:
                        result["reactions"] = max(result["reactions"], _parse_count(m.group(1)))
            if "comment" in ll:
                m = re.search(r"([\d,.]+[KkMm]?)", label)
                if m:
                    result["comments"] = max(result["comments"], _parse_count(m.group(1)))
            if "share" in ll:
                m = re.search(r"([\d,.]+[KkMm]?)", label)
                if m:
                    result["shares"] = max(result["shares"], _parse_count(m.group(1)))

        if result["reactions"] == 0 and result["comments"] == 0:
            for m in _ENGAGEMENT_PATTERN.finditer(article.get_text()):
                count = _parse_count(m.group(1))
                kind = m.group(2).lower()
                if "reaction" in kind or "like" in kind:
                    result["reactions"] = max(result["reactions"], count)
                elif "comment" in kind:
                    result["comments"] = max(result["comments"], count)
                elif "share" in kind:
                    result["shares"] = max(result["shares"], count)

        return result

    @staticmethod
    def _extract_url(article) -> Optional[str]:
        for sel in (
            "a[href*='/posts/']",
            "a[href*='story_fbid']",
            "a[href*='pfbid']",
            "a[href*='permalink']",
        ):
            el = article.select_one(sel)
            if el and el.get("href"):
                href = el["href"]
                if href.startswith("/"):
                    return f"https://www.facebook.com{href}"
                return href
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Desktop parser — sync Playwright ElementHandle
# ═══════════════════════════════════════════════════════════════════════════════

class DesktopParser:

    @staticmethod
    def parse_article_sync(article) -> Optional[dict]:
        """Full extraction for one post element (sync API)."""
        text = DesktopParser._extract_text(article)
        if not text:
            return None
        ts_iso, ts_raw = DesktopParser._extract_timestamp(article)
        if not ts_iso:
            ts_iso, ts_raw = DesktopParser._extract_timestamp_from_text(text)
        engagement = DesktopParser._extract_engagement(article)
        url = DesktopParser._extract_url(article)
        return {
            "text": text,
            "timestamp_iso": ts_iso,
            "timestamp_raw": ts_raw,
            "engagement": engagement,
            "post_url": url,
        }

    @staticmethod
    def _extract_text(article) -> Optional[str]:
        for sel in (
            "[data-ad-comet-preview='message']",
            "[data-ad-preview='message']",
            "[data-ad-comet-preview='message'] *",
            "[data-ad-preview='message'] span",
        ):
            msg_el = article.query_selector(sel)
            if msg_el:
                # text_content() avoids layout reflow (inner_text() forces reflow)
                text = msg_el.text_content()
                if text and len(text.strip()) > 5:
                    return text.strip()
        raw = article.text_content()
        return _extract_text_from_lines(raw)

    @staticmethod
    def _extract_timestamp(article) -> tuple[Optional[str], Optional[str]]:
        _ts_selectors_span = (
            "a[href*='/posts/'] span",
            "a[href*='permalink'] span",
            "a[href*='story_fbid'] span",
            "a[href*='pfbid'] span",
        )
        for sel in _ts_selectors_span:
            el = article.query_selector(sel)
            if el:
                raw = el.text_content().strip()
                if raw:
                    return normalize_timestamp(raw), raw

        _ts_selectors_link = (
            "a[href*='/posts/']",
            "a[href*='permalink']",
            "a[href*='story_fbid']",
            "a[href*='pfbid']",
        )
        for sel in _ts_selectors_link:
            el = article.query_selector(sel)
            if el:
                raw = el.text_content().strip()
                if raw and len(raw) < 50:
                    return normalize_timestamp(raw), raw

        time_el = article.query_selector("time[datetime]")
        if time_el:
            dt_attr = time_el.get_attribute("datetime")
            raw = time_el.text_content().strip()
            return dt_attr, raw

        try:
            ts_data = article.evaluate("""el => {
                const links = el.querySelectorAll('a[role="link"]');
                for (const a of links) {
                    const label = a.getAttribute('aria-label') || '';
                    const text = a.textContent.trim();
                    const combined = label || text;
                    if (!combined) continue;
                    const lower = combined.toLowerCase();
                    const dateSignals = [
                        'ago', 'yesterday', 'today', 'just now',
                        'january','february','march','april','may','june',
                        'july','august','september','october','november','december',
                        'jan ','feb ','mar ','apr ','may ','jun ',
                        'jul ','aug ','sep ','oct ','nov ','dec ',
                    ];
                    const timePattern = /\\b\\d{1,2}[hm]\\b|\\d{1,2}\\s*(hours?|minutes?|days?|weeks?)\\s*ago/i;
                    if (dateSignals.some(s => lower.includes(s)) || timePattern.test(combined)) {
                        return {label: label, text: text};
                    }
                }
                return null;
            }""")
            if ts_data:
                raw = ts_data.get("label") or ts_data.get("text", "")
                if raw:
                    return normalize_timestamp(raw), raw
        except Exception:
            pass

        links = article.query_selector_all("a[aria-label]")
        date_keywords = (
            "ago", "yesterday", "today",
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        )
        for link in links:
            label = link.get_attribute("aria-label")
            if label and any(kw in label.lower() for kw in date_keywords):
                return normalize_timestamp(label), label

        abbr = article.query_selector("abbr[data-utime]")
        if abbr:
            utime = abbr.get_attribute("data-utime")
            raw = abbr.text_content().strip()
            if utime:
                from datetime import datetime as dt_, timezone as tz_
                try:
                    iso = dt_.fromtimestamp(int(utime), tz=tz_.utc).isoformat()
                    return iso, raw
                except (ValueError, OSError):
                    pass

        return None, None

    @staticmethod
    def _extract_timestamp_from_text(text: str) -> tuple[Optional[str], Optional[str]]:
        """Extract timestamp from 'Submitted: ...' pattern in post text."""
        m = re.search(
            r"Submitted:\s+"
            r"((?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+\d{1,2},\s+\d{4}"
            r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)?)",
            text,
            re.I,
        )
        if m:
            raw = m.group(1).strip()
            return normalize_timestamp(raw), raw
        return None, None

    @staticmethod
    def _extract_engagement(article) -> dict:
        result = {"reactions": 0, "comments": 0, "shares": 0}

        elements = article.query_selector_all("[aria-label]")
        for el in elements:
            label = el.get_attribute("aria-label")
            if not label:
                continue
            ll = label.lower()
            for key in ("reaction", "like"):
                if key in ll:
                    m = re.search(r"([\d,.]+[KkMm]?)", label)
                    if m:
                        result["reactions"] = max(result["reactions"], _parse_count(m.group(1)))
            if "comment" in ll:
                m = re.search(r"([\d,.]+[KkMm]?)", label)
                if m:
                    result["comments"] = max(result["comments"], _parse_count(m.group(1)))
            if "share" in ll:
                m = re.search(r"([\d,.]+[KkMm]?)", label)
                if m:
                    result["shares"] = max(result["shares"], _parse_count(m.group(1)))

        if result["reactions"] == 0 and result["comments"] == 0:
            raw_text = article.text_content()
            for m in _ENGAGEMENT_PATTERN.finditer(raw_text):
                count = _parse_count(m.group(1))
                kind = m.group(2).lower()
                if "reaction" in kind or "like" in kind:
                    result["reactions"] = max(result["reactions"], count)
                elif "comment" in kind:
                    result["comments"] = max(result["comments"], count)
                elif "share" in kind:
                    result["shares"] = max(result["shares"], count)

        return result

    @staticmethod
    def _extract_url(article) -> Optional[str]:
        for sel in (
            "a[href*='/posts/']",
            "a[href*='permalink']",
            "a[href*='story_fbid']",
        ):
            el = article.query_selector(sel)
            if el:
                href = el.get_attribute("href")
                if href:
                    if href.startswith("/"):
                        return f"https://www.facebook.com{href}"
                    return href
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Basic Mobile parser (mbasic.facebook.com — BeautifulSoup)
# ═══════════════════════════════════════════════════════════════════════════════

class BasicMobileParser:

    @staticmethod
    def parse_page(html: str) -> tuple[list[dict], Optional[str]]:
        soup = BeautifulSoup(html, "html.parser")
        posts: list[dict] = []

        story_divs = soup.find_all("div", class_=re.compile(r"(story_body|_52jc|_5s6c)"))
        if not story_divs:
            story_divs = soup.find_all("article")
        if not story_divs:
            story_divs = soup.find_all("div", attrs={"data-ft": True})

        for div in story_divs:
            post = BasicMobileParser._parse_story(div)
            if post and post.get("text"):
                posts.append(post)

        next_url = None
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            if "see more" in text or "show more" in text or "older" in text:
                href = a["href"]
                if href.startswith("/"):
                    next_url = f"https://mbasic.facebook.com{href}"
                else:
                    next_url = href
                break

        return posts, next_url

    @staticmethod
    def _parse_story(div) -> Optional[dict]:
        text_parts = []
        for p in div.find_all(["p", "span"]):
            t = p.get_text(strip=True)
            if t and not _is_noise(t) and len(t) > 2:
                text_parts.append(t)

        if not text_parts:
            text_el = div.get_text(separator="\n", strip=True)
            lines = [ln for ln in text_el.split("\n") if not _is_noise(ln) and len(ln.strip()) > 2]
            text_parts = lines

        text = "\n".join(dict.fromkeys(text_parts))
        if not text or len(text) < 5:
            return None

        ts_raw = None
        ts_iso = None
        abbr = div.find("abbr")
        if abbr:
            utime = abbr.get("data-utime")
            ts_raw = abbr.get_text(strip=True)
            if utime:
                from datetime import datetime as dt_, timezone as tz_
                try:
                    ts_iso = dt_.fromtimestamp(int(utime), tz=tz_.utc).isoformat()
                except (ValueError, OSError):
                    pass
            elif ts_raw:
                ts_iso = normalize_timestamp(ts_raw)

        post_url = None
        for a in div.find_all("a", href=True):
            href = a["href"]
            if "/story.php" in href or "/permalink" in href or "/posts/" in href:
                if href.startswith("/"):
                    post_url = f"https://mbasic.facebook.com{href}"
                else:
                    post_url = href
                break

        engagement = {"reactions": 0, "comments": 0, "shares": 0}
        eng_text = div.get_text()
        for m in _ENGAGEMENT_PATTERN.finditer(eng_text):
            count = _parse_count(m.group(1))
            kind = m.group(2).lower()
            if "reaction" in kind or "like" in kind:
                engagement["reactions"] = max(engagement["reactions"], count)
            elif "comment" in kind:
                engagement["comments"] = max(engagement["comments"], count)
            elif "share" in kind:
                engagement["shares"] = max(engagement["shares"], count)

        return {
            "text": text,
            "timestamp_iso": ts_iso,
            "timestamp_raw": ts_raw,
            "engagement": engagement,
            "post_url": post_url,
        }
