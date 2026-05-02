# Freedom Wall Public Scraper

Collects publicly visible posts from Facebook Freedom Wall pages for academic research on student discourse analysis.

## Ethical Constraints

- **Public data only** — the scraper runs without login credentials
- **No authentication bypass** — if a page requires login, it is skipped
- **No private groups** — only public Facebook Pages are targeted
- **Rate-limited** — randomized delays between all actions
- **Data minimization** — only post text, timestamps, engagement counts, and post URLs are collected; no user profiles, names, or comment data
- **Academic use only** — this tool is built for the thesis research project at Saint Louis University

## Setup

```bash
# Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## Usage

```bash
# Scrape all configured targets
python main.py

# Scrape specific institutions
python main.py --targets FW-01 SLU

# Debug mode (visible browser)
python main.py --targets SLU --headed

# Custom post target
python main.py --target-posts 500

# Filter to latest semester
python main.py --semester-filter
```

## Output

Results are saved to `data/` as JSON files:

```
data/
  FW-01.json          # per-institution results
  FW-02.json
  ...
  SLU.json
  scrape_summary.json  # aggregate summary
```

Each file follows this schema:

```json
{
  "metadata": {
    "institution_code": "FW-01",
    "scrape_timestamp": "2026-05-01T15:30:00+08:00",
    "strategy_used": "desktop",
    "total_posts_collected": 47,
    "target_posts": 4000,
    "collection_status": "partial_login_wall"
  },
  "posts": [
    {
      "post_id": "a1b2c3d4e5f6g7h8",
      "text": "Post content here...",
      "timestamp_iso": "2026-04-28T14:22:00+08:00",
      "timestamp_raw": "3d",
      "engagement": {"reactions": 42, "comments": 15, "shares": 3},
      "post_url": "https://www.facebook.com/..."
    }
  ]
}
```

## Known Limitations

1. **Low post yield** — Facebook restricts unauthenticated access. Expect 10-200 posts per page, far below the 4,000 target.
2. **No historical depth** — only recently visible posts are reachable without login.
3. **DOM fragility** — Facebook changes its frontend frequently. Selectors may break without notice.
4. **Relative timestamps** — timestamps like "3d" are converted to approximate ISO dates.
5. **Incomplete engagement** — reaction/comment/share counts may not be visible without login.

## If the Scraper Yields Insufficient Data

See `scraping_strategy.md` Section 7 for escalation options including Meta Content Library API (academic access) and Apify (requires ethics disclosure).

## Project Structure

```
scraper_project/
├── main.py              # Entry point + CLI
├── scraper.py           # Playwright browser engine
├── parser.py            # DOM content extraction
├── utils.py             # Logging, retry, timestamps
├── config.py            # Configuration + target pages
├── requirements.txt     # Python dependencies
├── scraping_strategy.md # Full strategy document
├── README.md            # This file
├── data/                # Output directory
├── logs/                # Scrape logs
└── notebook/            # Analysis notebooks
```
