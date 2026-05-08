"""Sanitize the verbatim NIM API response cache for public release.

The raw cache (`vad_scoring/api_cache/raw_responses_researcher_*.jsonl`) stores
the full prompt-and-response for every batched VAD-scoring call. The prompts
contain post text (anonymized but still content), which exceeds what the
data-minimization commitment in the Method §Ethical-considerations subsection
permits to leave the team's environment.

This script replaces each record's `messages` array with a single
`prompt_sha256` field — the SHA-256 over the canonical-JSON representation of
the original messages list. That preserves the audit guarantee that a given
response was produced by a fixed prompt at a fixed model version, while
removing the prompt body itself.

Idempotent: re-running on an already-sanitized file leaves the file
unchanged, since records that already carry `prompt_sha256` are passed through.

Usage:
    python vad_scoring/sanitize_api_cache.py            # dry-run, prints summary
    python vad_scoring/sanitize_api_cache.py --apply    # write sanitized .jsonl in place
                                                          (originals copied to *.raw.bak first)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "vad_scoring" / "api_cache"


def canon_sha256(messages_list) -> str:
    """SHA-256 over a canonical JSON encoding of messages_list.

    Canonical = sort_keys, no extra whitespace, ensure_ascii false.
    """
    canon = json.dumps(messages_list, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def sanitize_record(rec: dict) -> tuple[dict, bool]:
    """Returns (new_record, changed).

    changed=False means rec was already sanitized (no `messages` field).
    """
    if "messages" not in rec:
        return rec, False
    new = dict(rec)
    new["prompt_sha256"] = canon_sha256(new.pop("messages"))
    return new, True


def process_file(path: Path, apply: bool) -> tuple[int, int]:
    """Returns (n_records, n_sanitized)."""
    if not path.exists():
        return 0, 0
    n_records = 0
    n_sanitized = 0
    out_lines = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                out_lines.append(line)
                continue
            n_records += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                out_lines.append(line)
                continue
            new, changed = sanitize_record(rec)
            if changed:
                n_sanitized += 1
                out_lines.append(json.dumps(new, ensure_ascii=False))
            else:
                out_lines.append(line)
    if apply and n_sanitized > 0:
        # Backup original (one-time; if backup already exists, leave it alone)
        backup = path.with_suffix(path.suffix + ".raw.bak")
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return n_records, n_sanitized


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Write changes in place. Originals saved as *.raw.bak.")
    args = parser.parse_args()

    if not CACHE_DIR.exists():
        print(f"no api_cache directory at {CACHE_DIR.relative_to(ROOT)}")
        return

    files = sorted(CACHE_DIR.glob("raw_responses_*.jsonl"))
    if not files:
        print(f"no raw_responses_*.jsonl under {CACHE_DIR.relative_to(ROOT)}")
        return

    mode = "APPLIED" if args.apply else "DRY-RUN"
    grand_records = 0
    grand_sanitized = 0
    for f in files:
        n, k = process_file(f, args.apply)
        grand_records += n
        grand_sanitized += k
        rel = f.relative_to(ROOT)
        if k == 0:
            print(f"  {rel}: {n} records, already sanitized")
        else:
            print(f"  {rel}: {k}/{n} records sanitized")

    print(f"\n[{mode}] api_cache sanitization — {grand_sanitized}/{grand_records} records "
          f"across {len(files)} file(s)")
    if not args.apply and grand_sanitized:
        print("re-run with --apply to write changes (originals copied to *.raw.bak)")


if __name__ == "__main__":
    main()
