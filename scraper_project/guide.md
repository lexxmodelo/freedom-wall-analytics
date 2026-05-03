# Freedom Wall Scraper — Setup & Usage Guide

**For:** Research team members running the scraper on their own machine  
**Maintained by:** Alexx Evan Modelo, SLU CS  
**Last updated:** 2026-05-04

---

## What This Does

This tool automatically scrolls through Facebook Freedom Wall pages and saves every post (text, timestamp, reactions) to a JSON file. It runs in the background — you can leave your computer and come back to results.

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

You should see a progress bar like this:
```
[SLU]  32%|████████          | 32/100 posts [01:24<02:45, 2.1s/post, net=8, scroll=12, sess=1, stale=0]
```

- **32/100** — posts collected so far out of the target
- **01:24** — time elapsed
- **02:45** — estimated time remaining
- **net=8** — posts captured passively from Facebook's network responses (not from DOM scraping)
- **scroll=12** — how many times it has scrolled in the current browser session
- **sess=1** — which browser session you're on (the scraper relaunches Chrome roughly every 100 scrolls)
- **stale=0** — consecutive scrolls with no new posts (0 = healthy, content still loading)

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

**About the periodic restart.** Roughly every 100 scrolls you'll see a line like `Restart cycle #1 — relaunching browser` followed by a brief pause and `Fast-forward in progress…`. This is the scraper deliberately recycling Chrome to sidestep the freeze that would otherwise hit at 200–600 scrolls. After a fast-forward (~1–2 minutes) it resumes collecting. **Don't stop the run when you see this** — it's working as designed.

**Estimated time per page:** 1.5–2.5 hours for 4,000 posts (the periodic restarts trade a little speed for not freezing on slower machines)  
**Estimated total (all 10 pages):** 15–25 hours (run one or two pages at a time)

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

### Progress bar shows very high ETA (50+ hours)
This is usually a transient slow patch right after a restart cycle (the fast-forward through duplicate posts is slow before it crosses into new content). Wait a minute or two — once fast-forward completes, the ETA recalculates and drops. If it stays stuck for more than 5 minutes, stop the run (`Ctrl+C`) and just rerun the same command — the scraper resumes from `data/{CODE}.jsonl` automatically.

### "Restart cycle" appears every few minutes
This is normal — the scraper recycles the browser roughly every 100 scrolls to avoid freezing. Each cycle adds ~1–2 minutes of fast-forward overhead but prevents the run from dying. Let it run.

### The scraper stops with "ScrollWatchdog fired" or freezes
The watchdog detects when Chrome stops responding and saves what it collected. This shouldn't happen with the current 100-scroll restart cap, but if it does:
1. Check `data/{CODE}.jsonl` — your collected posts are still there
2. Rerun the same command — it resumes from the JSONL
3. If it freezes repeatedly on the same scroll, contact the team lead with your `logs/` folder

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
