"""Post-process topic_labels.json (and downstream label fields) to redact
school demonyms and proper-name school references that the Llama-mediated
labelling stage produced before the demonym blocklist was in place.

Targets:
  - topic_modeling/outputs/<UNIV>/topic_labels.json   (label field)
  - topic_modeling/outputs/<UNIV>/topic_metadata.json (label field, if present)
  - dashboard/data/research/<UNIV>.json               (topics[*].label, posts[*].topic_label_model where present)
  - dashboard/data/institutional/<UNIV>.json          (topics[*].label, signals labels)
  - dashboard/data/_summary.json                      (topics_top3[*])
  - vad_scoring/results/researcher_*/<UNIV>_vad_scores.jsonl (topic_label per row)
  - validation/annotations/<UNIV>.jsonl              (topic_label_model per row)

Idempotent: safe to re-run. Replaces every blocklisted token with
[REDACTED_DEMONYM]; case-insensitive whole-word match.

Usage:
    python dashboard/etl/redact_demonyms.py            # dry-run, prints summary
    python dashboard/etl/redact_demonyms.py --apply    # writes changes in-place
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Blocklist: school demonyms and proper-name fragments that surface in
# Llama-generated topic labels for Philippine HEI Freedom Walls. Case-insensitive.
# Order matters: longer / more specific terms first so re.sub doesn't leave
# leftover fragments after a shorter match consumes the prefix.
BLOCKLIST = [
    # Demonyms (people-of-school nouns/adjectives)
    "Atenista",
    "Atenean",
    "Lasallista",
    "Lasallian",
    "La Sallian",
    "Tomasian",
    "Tomasino",
    "Louisian",
    "Aklenean",
    "Iskolar",
    "Iskolars",
    # School proper-names (full and short forms) — longer forms first.
    "Ateneo de Manila University",
    "Ateneo de Manila",
    "Ateneo",
    "De La Salle University",
    "De La Salle",
    "La Salle",
    "DLSU",
    "ADMU",
    "Lyceum of the Philippines",
    "Lyceum",
    "LPU",
    "Saint Louis University",
    "Saint Louis",
    "Far Eastern University",
    "Far Eastern",
    "FEU",
    "Caraga State University",
    "Caraga State",
    "University of the Philippines",
    "UP Diliman",
    "UP Los Baños",
    "UP Los Banos",
    "UP Baguio",
    "UPLB",
    "UPD",
    "UPB",
    "Benguet State University",
    "Benguet State",
    "BSU",
    "University of Baguio",
    # School-identifying program / unit acronyms surfaced in topic labels.
    "ACET",       # Ateneo College Entrance Test
    "AEGIS",      # Ateneo yearbook
    "IARFA",      # FEU Institute of Architecture and Fine Arts
    "CCJE",       # College of Criminal Justice Education (LPU-B)
    "JPL",        # appeared in PROV-PNSEC-1 (LPU-B) topic labels
]

# Compile once. \b on either side enforces whole-word match.
PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(term) for term in BLOCKLIST) + r")\b",
    flags=re.IGNORECASE,
)
REPLACEMENT = "[REDACTED_DEMONYM]"


def redact(s: str) -> tuple[str, int]:
    """Returns (redacted, count_of_substitutions)."""
    if not isinstance(s, str) or not s:
        return s, 0
    new, n = PATTERN.subn(REPLACEMENT, s)
    # Collapse runs of consecutive [REDACTED_DEMONYM] tokens that result from
    # multi-word matches (e.g., "Saint Louis University" matched as two terms).
    new = re.sub(r"(\[REDACTED_DEMONYM\]\s*){2,}", "[REDACTED_DEMONYM] ", new).strip()
    return new, n


def process_json_file(path: Path, key_paths: list[tuple[str, ...]], stats: dict, apply: bool) -> None:
    """Walk a JSON document and redact at each key_path tuple.

    key_paths examples:
      ("label",)                        — top-level "label" field
      ("topics", "*", "label")          — every topics[*].label
      ("posts", "*", "topic_label_model")
    """
    if not path.exists():
        return
    try:
        # Use utf-8-sig to handle the BOM that PowerShell write inserted earlier
        # in the rename pass; this is forward-compatible with utf-8-without-BOM.
        with path.open(encoding="utf-8-sig") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"  SKIP (parse error): {path.relative_to(ROOT)} — {e}")
        return

    changed = _walk_and_redact(data, key_paths, stats, str(path.relative_to(ROOT)))
    if changed and apply:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _walk_and_redact(node, key_paths, stats, file_label) -> bool:
    """Returns True if any value was modified."""
    changed = False
    for kp in key_paths:
        changed |= _apply_keypath(node, kp, stats, file_label)
    return changed


def _apply_keypath(node, kp, stats, file_label) -> bool:
    if not kp:
        return False
    head, *tail = kp
    changed = False
    if head == "*":
        if isinstance(node, list):
            for item in node:
                changed |= _apply_keypath(item, tail, stats, file_label)
        elif isinstance(node, dict):
            for v in node.values():
                changed |= _apply_keypath(v, tail, stats, file_label)
        return changed
    if not isinstance(node, dict) or head not in node:
        return False
    if not tail:
        # Leaf: redact this string field.
        original = node[head]
        new, n = redact(original)
        if n > 0:
            node[head] = new
            stats[file_label] += n
            changed = True
        return changed
    return _apply_keypath(node[head], tail, stats, file_label)


def process_jsonl_file(path: Path, fields: list[str], stats: dict, apply: bool) -> None:
    if not path.exists():
        return
    out_lines = []
    file_label = str(path.relative_to(ROOT))
    n_changed = 0
    try:
        with path.open(encoding="utf-8-sig") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip():
                    out_lines.append(line)
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    out_lines.append(line)
                    continue
                line_changed = False
                for field in fields:
                    if field in record:
                        new, n = redact(record[field])
                        if n > 0:
                            record[field] = new
                            n_changed += n
                            line_changed = True
                if line_changed:
                    out_lines.append(json.dumps(record, ensure_ascii=False))
                else:
                    out_lines.append(line)
    except (FileNotFoundError, PermissionError) as e:
        print(f"  SKIP: {file_label} — {e}")
        return

    if n_changed:
        stats[file_label] += n_changed
        if apply:
            path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Write changes in place (default: dry-run).")
    args = parser.parse_args()

    stats: dict[str, int] = defaultdict(int)

    # 1. topic_modeling outputs (one dir per university).
    topic_dir = ROOT / "topic_modeling" / "outputs"
    if topic_dir.exists():
        for univ_dir in sorted(topic_dir.iterdir()):
            if not univ_dir.is_dir():
                continue
            process_json_file(univ_dir / "topic_labels.json",
                              [("*", "label")], stats, args.apply)
            process_json_file(univ_dir / "topic_metadata.json",
                              [("*", "label"), ("*", "topic_label")], stats, args.apply)
            # Topic representative-document texts are post text and require
            # the same demonym treatment.
            process_json_file(univ_dir / "topic_rep_docs.json",
                              [("*", "*", "text"), ("*", "*", "doc")],
                              stats, args.apply)

    # 2. preprocessing outputs — primary research data; demonyms in `text`
    # field are redacted here per the manuscript anonymisation extension
    # (post-text demonyms previously treated as discourse content; now
    # explicitly redacted before public release).
    preproc_dir = ROOT / "preprocessing" / "output"
    if preproc_dir.exists():
        for f in sorted(preproc_dir.glob("FW-*_cleaned.json")):
            process_json_file(f, [("*", "text")], stats, args.apply)
        slu = preproc_dir / "SLU_cleaned.json"
        if slu.exists():
            process_json_file(slu, [("*", "text")], stats, args.apply)
        rej = preproc_dir / "_rejected.jsonl"
        if rej.exists():
            process_jsonl_file(rej, ["text", "text_preview"], stats, args.apply)

    # 3. dashboard data (research + institutional + summary).
    dash_research = ROOT / "dashboard" / "data" / "research"
    if dash_research.exists():
        for f in sorted(dash_research.glob("*.json")):
            process_json_file(f, [
                ("topics", "*", "label"),
                ("posts", "*", "text"),
                ("posts", "*", "topic_label"),
                ("posts", "*", "topic_label_model"),
            ], stats, args.apply)

    dash_inst = ROOT / "dashboard" / "data" / "institutional"
    if dash_inst.exists():
        for f in sorted(dash_inst.glob("*.json")):
            process_json_file(f, [
                ("topics", "*", "label"),
                ("posts", "*", "text"),
                ("posts", "*", "topic_label"),
                ("posts", "*", "topic_label_model"),
                ("signals", "*", "label"),
                ("signals", "*", "title"),
            ], stats, args.apply)

    process_json_file(ROOT / "dashboard" / "data" / "_summary.json",
                      [("*", "topics_top3", "*"), ("*", "topics_top3", "*", "label")],
                      stats, args.apply)

    # 4. VAD per-researcher results (jsonl, topic_label per row).
    vad_dir = ROOT / "vad_scoring" / "results"
    if vad_dir.exists():
        for f in sorted(vad_dir.glob("researcher_*/*_vad_scores.jsonl")):
            process_jsonl_file(f, ["topic_label"], stats, args.apply)

    # 5. Validation annotations (jsonl, topic_label_model per row).
    valid_dir = ROOT / "validation" / "annotations"
    if valid_dir.exists():
        for f in sorted(valid_dir.glob("*.jsonl")):
            process_jsonl_file(f, ["topic_label_model"], stats, args.apply)

    # Report.
    if not stats:
        print("no demonym matches found across the corpus")
        return
    total = sum(stats.values())
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n[{mode}] demonym-redaction summary — {total} substitutions across {len(stats)} files\n")
    for path, n in sorted(stats.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {n:>5}  {path}")
    if not args.apply:
        print("\nre-run with --apply to write changes")


if __name__ == "__main__":
    main()
