"""Regenerate 2-D UMAP projections per university for the dashboard cluster scatter.

Production BERTopic exports keywords/labels/assignments but not the underlying
2-D embedding coordinates. This script re-fits UMAP(n_components=2) using the
production embedding model and writes per-univ `umap_2d.json` aligned with
each university's `topic_assignments.json` post order.

Output schema:
    {
      "univ_code": "...",
      "n_posts": N,
      "params": {...},
      "coords": { post_id: [x, y], ... }
    }

After running, re-execute `build_dashboard_data.py` so the research-mode JSONs
pick up the new `umap_xy` arrays.

Dependencies (install once):
    pip install sentence-transformers umap-learn pyyaml

Usage:
    python dashboard/etl/export_umap_embeddings.py
    python dashboard/etl/export_umap_embeddings.py --univ CAR-PUB-1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PREPROC_DIR = ROOT / "preprocessing" / "output"
TOPIC_DIR = ROOT / "topic_modeling" / "outputs"
MAPPING_YAML = ROOT / "topic_modeling" / "configs" / "university_mapping.yaml"

UMAP_PARAMS = dict(n_components=2, n_neighbors=15, min_dist=0.05, metric="cosine", random_state=42)
EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def load_mapping() -> dict[str, str]:
    raw = yaml.safe_load(MAPPING_YAML.read_text(encoding="utf-8"))
    return {meta["code"]: filename for filename, meta in raw["mappings"].items() if meta.get("active", True)}


def export_one(univ_code: str, source_file: str, model, umap_module):
    base = TOPIC_DIR / univ_code
    assignments = json.loads((base / "topic_assignments.json").read_text(encoding="utf-8"))
    posts_idx = {p["post_id"]: p for p in json.loads((PREPROC_DIR / source_file).read_text(encoding="utf-8"))}

    ordered_ids, texts = [], []
    for a in assignments:
        pid = a["post_id"]
        src = posts_idx.get(pid)
        if not src:
            continue
        ordered_ids.append(pid)
        texts.append(src.get("text", ""))

    print(f"[UMAP] {univ_code}: embedding {len(texts)} posts...", flush=True)
    embs = model.encode(texts, batch_size=64, show_progress_bar=False, convert_to_numpy=True)
    print(f"[UMAP] {univ_code}: fitting UMAP(n_components=2)...", flush=True)
    reducer = umap_module.UMAP(**UMAP_PARAMS)
    xy = reducer.fit_transform(embs)

    out = {
        "univ_code": univ_code,
        "n_posts": len(ordered_ids),
        "params": UMAP_PARAMS,
        "coords": {pid: [float(x), float(y)] for pid, (x, y) in zip(ordered_ids, xy)},
    }
    (base / "umap_2d.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"[UMAP] {univ_code}: wrote {base / 'umap_2d.json'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--univ", action="append", help="Specific university code(s)")
    args = ap.parse_args()

    try:
        from sentence_transformers import SentenceTransformer
        import umap as umap_module
    except ImportError as e:
        print("Missing dependency. Install with:\n    pip install sentence-transformers umap-learn pyyaml", file=sys.stderr)
        print(f"Original error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[UMAP] loading model {EMBED_MODEL_NAME}...")
    model = SentenceTransformer(EMBED_MODEL_NAME)

    mapping = load_mapping()
    targets = args.univ if args.univ else sorted(mapping.keys())
    for code in targets:
        if code not in mapping:
            print(f"[UMAP] skip {code}: not in mapping")
            continue
        try:
            export_one(code, mapping[code], model, umap_module)
        except Exception as e:
            print(f"[UMAP] FAILED {code}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
