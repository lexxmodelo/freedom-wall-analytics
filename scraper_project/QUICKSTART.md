# Freedom Wall Scraper — Quickstart for Researchers

> You already have the repo. This gets you from zero to scraping in ~10 minutes.  
> Full details (troubleshooting, command reference, output format): see **`guide.md`**

---

## Step 1 — Open the project in VS Code

1. Open **VS Code**
2. Go to **File → Open Folder**
3. Select the `scraper_project` folder
4. Open the built-in terminal: **Terminal → New Terminal** (or `` Ctrl+` ``)

> All commands below are typed in that terminal.

---

## Step 2 — Install Python (if you don't have it)

Check first:
```
python --version
```

If you get an error, download Python from **[python.org/downloads](https://www.python.org/downloads/)**.  
During install, **tick "Add Python to PATH"** — do not skip this.  
Restart VS Code after installing.

---

## Step 3 — Install dependencies

Run these two commands in the terminal, one at a time:

```
pip install playwright beautifulsoup4 tqdm pandas httpx
```
```
python -m playwright install chromium
```

The second one downloads ~300 MB. Wait for it to finish.

---

## Step 4 — Install Google Chrome (if you don't have it)

Download from **[google.com/chrome](https://www.google.com/chrome/)** and install normally.  
The scraper uses your real Chrome — it needs to be installed.

---

## Step 5 — Log in to Facebook (one-time)

```
python extract_cookies.py
```

A Chrome window opens. **Do not close it.**

1. Log in to Facebook with your account
2. Complete CAPTCHA or 2FA if it appears
3. Wait until you see the Facebook home feed
4. Go back to the terminal — it will say **"Cookies saved"** and close automatically

> Your login is saved to `cookies.json`. Keep this file private — do not share it or push it to GitHub.

---

## Step 6 — Pick your Freedom Wall and start scraping

```
python pick.py
```

A menu appears:

```
  #    Code     Institution
  --   ------   ------------------------------------------
  1    SLU      Saint Louis University (Baguio)
  2    FW-01    Ateneo de Manila University
  3    FW-02    UP Diliman
  ...
```

- Type the **number** of your assigned page and press Enter
- Press Enter again to keep the default target (4,000 posts)
- Type **Y** to confirm and start

You'll see logging like this (one line per pagination request, ~3 posts each):
```
[SLU][graphql_httpx] harvesting tokens...
[SLU][graphql_httpx] harvested tokens: friendly=ProfileCometTimelineFeedRefetchQuery ...
[SLU][graphql_httpx] iter=10 total=30 (+3) next_cursor=Cg8Ob3JnYW5pY...
[SLU][graphql_httpx] iter=20 total=60 (+3) next_cursor=Cg8Ob3JnYW5pY...
[SLU] Checkpoint: +30 new posts (total=60) -> data/SLU.jsonl
```

Leave the terminal running. It takes roughly **1–1.5 hours** per page (4,000 posts).  
Results are saved to the `data/` folder when done.

> **Two-phase scraping.** Each run starts with a brief Chrome session (~15 s) to capture Facebook's pagination tokens, then runs the rest as direct API calls — no scrolling, no DOM. Chrome stays open as a thin HTTP client. Total memory is bounded at ~1.5 GB regardless of post count.

> **If your run crashes or you stop it,** just rerun the same command. The scraper resumes from `data/{CODE}.jsonl` automatically. The first ~30 minutes after a resume show `+0` posts per iteration — that's the scraper fast-forwarding past the posts you already have. It will start adding new content again once it crosses your previous high-water mark.

---

## That's it

Your output files will be at:
```
data/FW-02.json     ← final deliverable (sent to team lead)
data/FW-02.jsonl    ← live append-only log (kept in case you want to resume)
```

Send the `.json` file to the team lead when it's done.

---
