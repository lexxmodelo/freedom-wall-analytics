# Freedom Wall Scraper — Setup & Usage Guide

**For:** Research team members running the scraper on their own machine  
**Maintained by:** Alexx Evan Modelo, SLU CS  
**Last updated:** 2026-05-04

---

## What This Does

This tool collects every post (text, timestamp, reactions) from Facebook Freedom Wall pages and saves them to a JSON file. It runs in the background — you can leave your computer and come back to results.

### How It Works (One-Minute Overview)

The scraper has a **chain of strategies**. It tries them in order; each falls through to the next if it can't deliver:

1. **`desktop_graphql_httpx`** *(default, recommended).* Briefly opens Chrome (~15 s) to capture Facebook's pagination tokens, then closes the browser as a renderer and replays the API calls directly. No scrolling, no DOM, memory stays flat at ~1.5 GB regardless of post count. Reaches 4,000 posts on any laptop.
2. **`desktop`** *(fallback).* The original full-Chrome approach: scrolls the page, parses the DOM. Works but freezes around 1,700 posts on lower-RAM laptops, which is why it's now a fallback rather than the default.
3. `basic_mobile_httpx`, `basic_mobile` — *(currently inactive — Facebook is gating mbasic for modern user agents).* Kept as cheap probes in case Facebook re-enables them.

You don't have to pick a strategy — the scraper tries them in order automatically. The `--strategies` flag exists if you want to force a specific one (see Command Reference).

---

## Part 1 — One-Time Setup

Do this once on each new machine. You won't need to repeat it.

### Step 1 — Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download **Python 3.11** or newer (avoid 3.13+ if you see issues)
3. During install, **tick "Add Python to PATH"** — this is important
4. Open a new Command Prompt and confirm it works:
   ```
   python --version
   ```
   You should see something like `Python 3.11.9`

> **Windows users:** Use **Command Prompt** (cmd.exe), not PowerShell, for all commands in this guide.

---

### Step 2 — Download the Scraper Files

Get the scraper folder from the research team (via USB, Google Drive, or Git). Place it somewhere easy to find, for example:
```
C:\Users\YourName\Documents\Research\scraper_project\
```

---

### Step 3 — Install Dependencies

Open Command Prompt, navigate to the scraper folder, then run:

```cmd
cd C:\Users\YourName\Documents\Research\scraper_project
pip install playwright beautifulsoup4 tqdm pandas httpx
python -m playwright install chromium
```

This downloads Playwright's browser engine (~300 MB). Only needed once.

> **If `pip` is not found:** Try `python -m pip install ...` instead.

---

### Step 4 — Install Google Chrome

The scraper uses your real Google Chrome (not the built-in Playwright browser). If Chrome is not installed:

1. Download from [google.com/chrome](https://www.google.com/chrome/)
2. Install normally

---

## Part 2 — Login (One-Time Per Machine)

The scraper needs your Facebook login saved so it can access the pages. This is a one-time step per machine — the login stays saved even after you restart.

### Step 5 — Extract Cookies (Login)

```cmd
python extract_cookies.py
```

A Chrome window will open. **Do not close it.**

1. Log into Facebook normally (username + password)
2. Complete any CAPTCHA or 2FA if asked
3. Wait until you see the Facebook home feed
4. Go back to Command Prompt — it will say **"Cookies saved"** and close automatically

> **Important:** Use a real Facebook account. The scraper only reads public pages — it does not post, message, or interact with anything.

Your login is saved to `cookies.json` in the scraper folder. Keep this file private (do not share it).

---

## Part 3 — Running the Scraper

### Step 6 — Run a Quick Test First

Before a full run, do a small test to make sure everything works.

**Easy way — interactive menu (recommended):**
```cmd
python pick.py
```
A menu appears. Select `1` (SLU), type `50` for target posts, and confirm.

**Manual way — command line:**
```cmd
python main.py --cookies cookies.json --targets SLU --target-posts 50
```

You should see logging like this:
```
[SLU][graphql_httpx] harvesting tokens...
[SLU][graphql_httpx] harvested tokens: friendly=ProfileCometTimelineFeedRefetchQuery doc_id=2654...
[SLU][graphql_httpx] iter=10 total=30 (+3) next_cursor=Cg8Ob3JnYW5pY19jdXJzb3IJ
[SLU][graphql_httpx] iter=20 total=60 (+3) next_cursor=Cg8Ob3JnYW5pY19jdXJzb3IJ
[SLU] Checkpoint: +30 new posts (total=60) -> data/SLU.jsonl
```

Reading the lines:
- **`harvesting tokens`** — brief Chrome session (~15 s) to capture pagination tokens
- **`harvested tokens`** — capture succeeded; the rest of the run is API replay
- **`iter=N total=M (+K)`** — pagination iteration N has run; collected M posts so far; gained K *new* posts on this iteration. Facebook returns ~3 posts per pagination call.
- **`+0`** is normal during fast-forward (when resuming a previous run, the scraper paginates past posts you already have — see "Resuming a run" below)
- **`Checkpoint`** — the `data/{CODE}.jsonl` file just got flushed (every 30 s while new posts arrive)

If `desktop_graphql_httpx` can't harvest tokens (rare — usually means Facebook changed something), you'll see a `falling through to next strategy` line and the scraper switches to the `desktop` (browser-scrolling) path — which is the older approach with `scroll=`/`stale=` progress fields:
```
[SLU]  32%|████████          | 32/100 posts [01:24<02:45, 2.1s/post, scroll=12, sess=1, stale=0]
```

When done, check the `data/` folder — you should see `SLU.json` (final) and `SLU.jsonl` (live log).

---

### Step 7 — Full Production Run

**Easy way — interactive menu (recommended for all researchers):**
```cmd
python pick.py
```
The menu lists all 10 Freedom Walls by number. Type your assigned number and press Enter. Each researcher on their own machine runs `pick.py` and picks a different page — no command-line arguments needed.

**Manual way — command line:**
```cmd
python main.py --cookies cookies.json --targets SLU FW-01 FW-02
```

**Full list of page codes:**

| Code  | Institution |
|-------|-------------|
| SLU   | Saint Louis University (Baguio) |
| FW-01 | Ateneo de Manila University |
| FW-02 | UP Diliman |
| FW-03 | Far Eastern University |
| FW-04 | UP Los Baños |
| FW-05 | Lyceum of the Philippines |
| FW-06 | Caraga State University |
| FW-07 | University of the Philippines Baguio |
| FW-08 | Benguet State University |
| FW-09 | University of Baguio |

---

### Step 8 — Let It Run

The scraper runs in the background. You can minimize the Command Prompt window.

- **Do not close the Command Prompt** — this will stop the scraper
- Do not put the laptop to sleep during a run
- Progress auto-saves every 30 seconds to `data/{CODE}.jsonl` — if it crashes, just rerun the same command and it resumes from where it left off

**Resuming a run.** If you stop the scraper (Ctrl+C) or it crashes, just rerun the same command. The scraper reads `data/{CODE}.jsonl`, pre-loads everything you collected, and continues. The first ~5–30 minutes after a resume show `+0` posts per iteration — that's the fast-forward through Facebook's pagination cursors back to your high-water mark. It's not stuck; the dedupe filter is just rejecting posts you already have. Once it crosses your previous total, you'll start seeing `+3` per iteration again.

**Token refresh.** Facebook's session tokens (`fb_dtsg`) eventually expire. If they do mid-run, you'll see `tokens aged out` followed by another `harvesting tokens` cycle (~15 s). The default is to proactively refresh after 4 hours, but reactive refresh on actual expiry kicks in earlier if needed. Either way, the run continues without losing posts.

**About browser restarts (fallback strategy only).** If the scraper ever falls through to `desktop` (the old DOM-scrolling strategy), you'll see `Restart cycle #1 — relaunching browser` lines. These are triggered when:
- The browser hits 500 scrolls in a single session
- The dedupe set hasn't grown in 50 consecutive scrolls
- Heap usage exceeds 700 MB
- The 90-second freeze watchdog fires

This shouldn't normally happen — `desktop_graphql_httpx` is the default and it doesn't scroll-and-render after harvest. If you see fallback restarts, the harvest probably failed; the scraper still works but is now using the slower DOM path. Send the team lead your `logs/` folder if it persists.

**Estimated time per page:** 1–1.5 hours for 4,000 posts (about 1 post/sec via the new strategy)  
**Estimated total (all 10 pages):** 10–15 hours (run one or two pages at a time)  
**Memory footprint:** ~1.5 GB total (Chrome stays flat — no growth with post count)

---

## Part 4 — Finding Your Results

All output goes to the `data/` folder inside the scraper directory.

| File | What It Is |
|------|-----------|
| `data/SLU.json` | **Final deliverable** — full results with metadata, written when the scrape finishes. This is the file you send to the team lead. |
| `data/SLU.jsonl` | **Live append-only log** — one post per line, written every 30 seconds during the run. Used for crash recovery; rerunning the same command picks up here. |
| `data/scrape_summary.json` | Summary of all pages scraped in a session |
| `logs/scrape_YYYYMMDD_HHMMSS.log` | Detailed log of the entire run |

> Older versions of the scraper used `data/SLU_checkpoint.json`. If you see that file from a previous run, the scraper will read it once and convert it into `SLU.jsonl` automatically — no manual action needed.

### What Each JSON Post Looks Like

```json
{
  "text": "Submitted: April 29, 2026\nTo the person who borrowed my notes...",
  "timestamp_iso": "2026-04-29T00:00:00+08:00",
  "timestamp_raw": "April 29, 2026",
  "engagement": {
    "reactions": 47,
    "comments": 12,
    "shares": 3
  },
  "post_url": null,
  "post_id": "a3f1b2c4d5e6f7a8"
}
```

---

## Part 5 — Troubleshooting

### "cookies.json not found" or "0 posts collected"
Your login may have expired. Re-run Step 5:
```cmd
python extract_cookies.py
```

### Chrome opens but immediately closes (during cookie extraction)
Facebook may have flagged the login. Try:
1. Log into Facebook normally in your regular Chrome browser first
2. Then run `extract_cookies.py` again

### Very slow progress or "stale=60 — stopping"
The page may not have enough posts. The scraper will stop gracefully and save what it found. Check `data/{CODE}.json` for partial results.

### "ModuleNotFoundError: No module named playwright"
Run the install commands from Step 3 again. Make sure you're in the right folder.

### The laptop is running out of RAM
- Close other programs (especially other Chrome windows and browser tabs)
- Run only one scrape at a time
- Do not open heavy applications while scraping

### Many `+0` iterations after resuming a run
This is fast-forward — Facebook's cursor pagination starts at the top of the feed, so the scraper has to walk past every post you already collected before finding new ones. For a 2,000-post resume, expect ~30 minutes of `+0` lines before productive work resumes. Not stuck — the dedupe filter is doing its job.

### "tokens aged out" or "FB error envelope" mid-run
The scraper will automatically re-harvest fresh tokens (~15 s) and continue. Nothing for you to do. If re-harvest fails repeatedly (you see `harvest failed (3/3) — falling through`), the scraper switches to the `desktop` fallback strategy, which still works — just slower. Send the team lead your `logs/` folder if this happens.

### "harvest failed" → falls through to desktop (DOM-scrolling) strategy
The `desktop_graphql_httpx` strategy needs a fresh authenticated browser session to capture Facebook's pagination tokens. If your `cookies.json` is stale, the page won't render the authenticated feed and harvest fails. Re-run `python extract_cookies.py` and try again.

### "Restart cycle" appears (only on the `desktop` fallback strategy)
Restarts are part of the fallback path. If you see them happening regularly, your cookies might be stale (forcing fallback) or Facebook may have changed something that broke the new strategy. Stop the run (`Ctrl+C`), refresh your cookies, and rerun. If it still falls through to desktop, send your `logs/` folder to the team lead.

---

## Part 6 — Command Reference

```cmd
# Full run (all pages, 4000 posts each)
python main.py --cookies cookies.json

# Single page test
python main.py --cookies cookies.json --targets SLU --target-posts 100

# Multiple specific pages
python main.py --cookies cookies.json --targets FW-01 FW-02 SLU

# Show browser window while running (for debugging)
python main.py --cookies cookies.json --targets SLU --headed

# Custom output folder
python main.py --cookies cookies.json --output-dir C:\MyResults

# Force a specific strategy (testing/debugging only — defaults are fine)
python main.py --cookies cookies.json --targets SLU --strategies desktop_graphql_httpx
python main.py --cookies cookies.json --targets SLU --strategies desktop
```

---

## Part 7 — Data Privacy Notes

- The scraper only reads **public** Facebook pages — it does not access private profiles or messages
- `cookies.json` contains your Facebook session — **keep it private, do not share it**
- All scraped data is stored locally on your machine — nothing is uploaded anywhere
- Collected posts are anonymized in research outputs (page codes instead of institution names)

---

## Quick Checklist for a New Machine

- [ ] Python installed and `python --version` works
- [ ] Scraper folder copied to the machine
- [ ] `pip install playwright beautifulsoup4 tqdm pandas httpx` done
- [ ] `python -m playwright install chromium` done
- [ ] Google Chrome installed
- [ ] `python extract_cookies.py` done — "Cookies saved" message appeared
- [ ] Quick test passed: `python main.py --cookies cookies.json --targets SLU --target-posts 50`
- [ ] `data/SLU.json` exists with posts inside (and `data/SLU.jsonl` next to it)

---

*For issues, contact Alexx Evan Modelo or check `logs/` for the detailed error log.*
