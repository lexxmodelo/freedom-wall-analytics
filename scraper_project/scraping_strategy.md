# Scraping Strategy: Freedom Wall Public Data Collection

**Date:** May 1, 2026  
**Status:** Pre-execution — awaiting team review  
**Ethical Posture:** Public-only, unauthenticated, academic research

---

## 1. Data Source Assessment

### 1.1 Target: Facebook Public Pages

Ten Freedom Wall Facebook pages are targeted. Nine are anonymized with codes (FW-01 through FW-09); one (SLU) is identified as the researchers' own institution.

**Fundamental Constraint:** Facebook actively restricts unauthenticated access to page content. As of 2025-2026, visiting a Facebook page without login typically results in:

1. A brief window (2-10 seconds) where some posts are visible
2. A full-screen login modal covering all content
3. Limited or no infinite scroll capability
4. Aggressive rate limiting and bot detection

This means the scraper will collect **significantly fewer posts than the 10,000/university target** in most cases without login. The team must plan for this reality.

### 1.2 Realistic Yield Estimates

| Scenario | Expected Posts per Page | Notes |
|---|---|---|
| Best case (page fully public, no modal) | 50-200 | Rare for active pages |
| Typical case (modal dismissable) | 10-50 | Most likely outcome |
| Worst case (immediate login wall) | 0-5 | Possible for /p/ format URLs |

**If these yields are insufficient**, the team has three escalation options (documented in Section 7).

---

## 2. Legal and Ethical Compliance

### 2.1 Legal Basis

- **Philippine Data Privacy Act (RA 10173):** Processing publicly available personal information is permitted for legitimate research purposes, provided data minimization and proportionality principles are followed.
- **Facebook Terms of Service:** Automated scraping is prohibited by Facebook's ToS. However, academic research on public content has been recognized by courts (e.g., *hiQ Labs v. LinkedIn*) as potentially overriding ToS restrictions for publicly accessible data.
- **Institutional Position:** This scraper collects only text, timestamps, and engagement counts from public pages. No user profiles, comments, or private data are accessed.

### 2.2 Ethical Safeguards (Enforced in Code)

| Safeguard | Implementation |
|---|---|
| No authentication | Scraper launches with clean browser profile, no cookies, no tokens |
| No login bypass | If login wall appears, scraper stops — does not enter credentials |
| No private content | Only `div[role="article"]` elements visible to unauthenticated users |
| Rate limiting | 3-7 second delay between scroll actions; 60-120 second delay between pages |
| Data minimization | Only 4 fields collected: text, timestamp, engagement, post URL |
| No user data | Usernames, profile URLs, and commenter info are never collected |
| Anonymization | Institution identifiers stripped in output metadata |

---

## 3. Scraping Approach

### 3.1 Technology Stack

- **Playwright** (async, Chromium): Handles JavaScript-rendered Facebook content
- **BeautifulSoup4**: Fallback HTML parsing when Playwright DOM queries fail
- **Python 3.10+**: asyncio-native, no compatibility shims needed

### 3.2 Multi-Strategy Architecture

The scraper attempts three strategies in sequence, stopping at the first that yields results:

```
Strategy 1: Desktop Facebook (www.facebook.com)
  → Load page → Dismiss modal → Scroll → Extract articles
  → Best for: Pages that allow modal dismissal

Strategy 2: Mobile Facebook (mbasic.facebook.com)
  → Load basic HTML page → Follow pagination links
  → Best for: Pages where desktop is blocked
  → Simpler DOM, less JavaScript dependency

Strategy 3: Direct HTML Fetch (no browser)
  → HTTP GET → Parse server-rendered HTML
  → Best for: Extracting whatever Facebook embeds for SEO
  → Very limited yield but zero bot-detection risk
```

### 3.3 DOM Extraction Strategy

Facebook uses obfuscated CSS class names that change without notice. The scraper uses **stable selectors**:

| Element | Primary Selector | Fallback |
|---|---|---|
| Post container | `div[role="article"]` | `div[data-ad-comet-preview="message"]` |
| Post text | Inner text of article, filtered | Regex on raw HTML for long text blocks |
| Timestamp | `a[href*="/posts/"] > span`, `time[datetime]` | `abbr[data-utime]`, aria-label parsing |
| Engagement | `span[aria-label*="reaction"]` | Regex for patterns like `1.2K` near reaction icons |
| Post URL | `a[href*="/posts/"]`, `a[href*="permalink"]` | Constructed from post ID |

### 3.4 Modal/Overlay Handling

```
1. Wait 2s after page load
2. Check for cookie consent → click "Allow" / "Accept"
3. Check for login modal → click "Close" / press Escape
4. If modal reappears after scroll → attempt dismiss again (max 3 times)
5. If modal is undismissable → mark page as login-blocked, save collected posts
```

---

## 4. Adaptive Collection Strategy

### 4.1 Three-Tier Fallback

```
Tier 1: TARGET MODE
  Goal: Collect target_posts (default: 4000)
  Method: Scroll until target reached or login wall hit
  Stop condition: target reached OR max_scrolls exceeded OR login blocked

Tier 2: SEMESTER MODE (fallback if Tier 1 yields < min_threshold)
  Goal: Collect all posts within current semester window
  Method: Filter collected posts by date range
  Window: AY 2024-2025 (June 2024 – May 2025)

Tier 3: EXHAUSTIVE MODE (fallback if Tier 2 yields < min_threshold)
  Goal: Collect everything visible
  Method: All strategies, no date filter, retry with longer delays
  This is the last resort — whatever we get is what we have
```

### 4.2 Stopping Conditions

The scraper stops scrolling when ANY of these conditions is met:

1. Target post count reached
2. Login wall becomes impassable (3 consecutive failed dismissals)
3. Max scroll attempts reached (default: 200)
4. No new posts found after 5 consecutive scrolls (page end)
5. Scraping duration exceeds timeout (default: 10 minutes per page)

---

## 5. Rate Limiting and Retries

### 5.1 Rate Limiting

| Action | Delay |
|---|---|
| Between scrolls | 3-7 seconds (randomized) |
| Between pages | 60-120 seconds (randomized) |
| After modal dismiss | 2-4 seconds |
| After strategy switch | 30-60 seconds |

### 5.2 Retry Logic

- Network errors: retry 3 times with exponential backoff (5s, 15s, 45s)
- Timeout errors: retry 2 times with 30s wait
- Login wall: no retry (strategy switch instead)
- Bot detection (CAPTCHA): stop immediately, log, move to next page

---

## 6. Output Schema

### 6.1 Per-Page JSON

```json
{
  "metadata": {
    "institution_code": "FW-01",
    "scrape_timestamp": "2026-05-01T15:30:00+08:00",
    "strategy_used": "desktop",
    "total_posts_collected": 47,
    "target_posts": 4000,
    "collection_status": "partial_login_wall",
    "scraper_version": "1.0.0",
    "duration_seconds": 245
  },
  "posts": [
    {
      "post_id": "sha256_hash_of_text",
      "text": "...",
      "timestamp_iso": "2026-04-28T14:22:00+08:00",
      "timestamp_raw": "3 days ago",
      "engagement": {
        "reactions": 42,
        "comments": 15,
        "shares": 3
      },
      "post_url": "https://www.facebook.com/..."
    }
  ]
}
```

### 6.2 Aggregate Summary

After all pages are scraped, a `scrape_summary.json` is generated:

```json
{
  "total_pages_attempted": 10,
  "total_pages_successful": 8,
  "total_posts_collected": 423,
  "pages": [
    {"code": "FW-01", "posts": 47, "status": "partial_login_wall"},
    {"code": "FW-02", "posts": 0, "status": "fully_blocked"},
    ...
  ]
}
```

---

## 7. Escalation Options (If Public Scraping Fails)

If the unauthenticated approach yields insufficient data (< 100 posts per institution):

### Option A: Apify with Authentication (Requires Ethics Disclosure)

Use Apify's Facebook Page Scraper with a session cookie. This accesses content through an authenticated session. **Must be disclosed in the ethics section** of the paper. The data is still "publicly accessible" but accessed through an authenticated channel.

**Estimated yield:** 5,000-10,000+ posts per page  
**Cost:** ~$49/month Apify subscription  
**Ethics impact:** Requires amendment to IRB application

### Option B: Meta Content Library API (Academic Access)

Apply for Meta's Content Library API, which provides structured access to public page content for academic researchers. **Requires institutional application and approval.**

**Estimated yield:** Full page history  
**Cost:** Free for approved researchers  
**Timeline:** 2-6 weeks for approval  
**Ethics impact:** Fully compliant — Meta's own research API

### Option C: Manual Collection with Browser Extension

Use a browser extension (e.g., Facebook Page Post Scraper) while logged in to manually export posts. **The researcher uses their own account and collects public page content.**

**Estimated yield:** Variable, depends on manual effort  
**Cost:** Free  
**Ethics impact:** Low — researcher accessing public content through normal browser use

### Recommendation

**Start with the automated public scraper (this system).** Measure actual yield. If insufficient, pursue Option B (Meta Content Library) as the ethically strongest alternative, with Option A as a faster fallback.

---

## 8. Known Limitations

1. **Post count will be far below target.** The 4,000-10,000 posts/university target from the proposal is not achievable through unauthenticated scraping alone.
2. **Historical posts may not be accessible.** Facebook's public view typically shows recent posts. Posts from 2023-2024 may not be reachable through scrolling.
3. **Engagement metrics may be incomplete.** Reaction counts are not always visible without login.
4. **Timestamps may be relative.** Facebook shows "3d" or "2w" instead of exact dates. The parser converts these to approximate ISO timestamps, but precision is limited.
5. **DOM changes may break selectors.** Facebook updates its frontend frequently. The parser uses multiple fallback strategies, but some may stop working without notice.
6. **Bot detection.** Facebook may detect automated browsing and serve CAPTCHAs or block access entirely. The scraper cannot bypass these.

---

*This strategy document must be reviewed and approved by the research team before execution begins.*
