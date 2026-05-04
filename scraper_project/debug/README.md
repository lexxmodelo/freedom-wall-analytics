# Debug Scripts

One-off diagnostic tools used during development. Not imported by the main
scraper. Each is a standalone Playwright session that inspects the DOM
structure of a Facebook page to validate selectors / parsing assumptions.

## Running

These scripts open `cookies.json` with a **relative path**, so always run
them from the **project root** — never from inside `debug/`:

```bash
# Correct
python debug/debug_dom.py

# Wrong — will fail to find cookies.json
cd debug && python debug_dom.py
```

## Files

| Script | Purpose |
|---|---|
| `debug_dom.py`  | Inspect `[role='article']` elements; understand comment vs post nesting |
| `debug_dom2.py` | DOM-shape probe for an early parser variant |
| `debug_dom3.py` | DOM-shape probe for a later parser variant |
| `debug_dom4.py` | DOM-shape probe used while diagnosing freeze cliffs |

These scripts were last useful around May 1–2, 2026 (during desktop
strategy DOM extraction development). They may not match current FB DOM
shapes, but they're kept as a starting point for future diagnostics.
