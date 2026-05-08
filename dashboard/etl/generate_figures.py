"""Generate manuscript Figures 5 and 6 as print-quality PNGs.

Figure 5 — Corpus-wide VAD scatter (Valence x Arousal, marker size encodes Dominance).
            Decimated to 1,500 representative points. Plain-English quadrant labels.
Figure 6 — Topic-by-VAD heatmap (rows = topics with >= 50 posts; cols = V, A, D;
            cell color = mean dimension value). Sorted by mean Valence ascending.

Reads:
  vad_scoring/results/researcher_*/<UNIV>_vad_scores.jsonl    (per-post V/A/D + topic_label)

Writes:
  docs/figures/figure_05_vad_scatter.png
  docs/figures/figure_06_topic_heatmap.png

Usage:
    python dashboard/etl/generate_figures.py
"""
from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
VAD_DIR = ROOT / "vad_scoring" / "results"
OUT_DIR = ROOT / "docs" / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Paper-grade defaults: serif body, sans for chart text. Small but legible.
plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 9,
    "axes.titlesize": 10.5,
    "axes.labelsize": 9.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
})

DECIMATE_N = 1500
MIN_POSTS_PER_TOPIC = 50
RNG_SEED = 42


def load_all_vad() -> list[dict]:
    """Walk every researcher_*/  *_vad_scores.jsonl and concatenate."""
    rows: list[dict] = []
    for jsonl in sorted(VAD_DIR.glob("researcher_*/*_vad_scores.jsonl")):
        with jsonl.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


# --------------------------------------------------------------------------- #
# Figure 5 — Corpus-wide VAD scatter                                          #
# --------------------------------------------------------------------------- #

def figure_5(rows: list[dict]) -> Path:
    pts = [(r["V"], r["A"], r["D"]) for r in rows
           if r.get("V") is not None and r.get("A") is not None and r.get("D") is not None]
    if len(pts) > DECIMATE_N:
        random.Random(RNG_SEED).shuffle(pts)
        pts = pts[:DECIMATE_N]
    V = np.array([p[0] for p in pts]) + np.random.RandomState(RNG_SEED).uniform(-0.18, 0.18, len(pts))
    A = np.array([p[1] for p in pts]) + np.random.RandomState(RNG_SEED + 1).uniform(-0.18, 0.18, len(pts))
    D = np.array([p[2] for p in pts])

    fig, ax = plt.subplots(figsize=(6.6, 4.6))

    # Quadrant guide lines at neutral (5).
    ax.axvline(5, color="#cbcbd1", lw=0.6, zorder=0)
    ax.axhline(5, color="#cbcbd1", lw=0.6, zorder=0)

    # Color by valence (cool -> warm), size by dominance (10 .. 90).
    sizes = 10 + ((D - 1) / 8) * 80
    sc = ax.scatter(V, A, c=V, cmap="RdYlBu_r", vmin=1, vmax=9,
                    s=sizes, alpha=0.55, linewidths=0, zorder=2)

    cb = fig.colorbar(sc, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label("Valence (1 negative — 9 positive)", fontsize=8.5)
    cb.ax.tick_params(labelsize=7.5)
    cb.outline.set_linewidth(0.4)

    # Plain-English quadrant labels (manuscript caption phrasing).
    ax.text(7.5, 8.5, "Empowered & engaged", ha="center", va="center",
            fontsize=8.5, color="#1f6f43", weight="600", alpha=0.85)
    ax.text(2.5, 8.5, "Stressed but constrained", ha="center", va="center",
            fontsize=8.5, color="#a83032", weight="600", alpha=0.85)
    ax.text(7.5, 1.6, "Calm & in control", ha="center", va="center",
            fontsize=8.5, color="#2a4d8a", weight="600", alpha=0.85)
    ax.text(2.5, 1.6, "Helpless & quiet", ha="center", va="center",
            fontsize=8.5, color="#5a4a78", weight="600", alpha=0.85)

    # Marker-size legend (Dominance) — placed below the plot to clear quadrant labels.
    legend_handles = [
        plt.scatter([], [], s=10, alpha=0.55, color="#999"),
        plt.scatter([], [], s=50, alpha=0.55, color="#999"),
        plt.scatter([], [], s=90, alpha=0.55, color="#999"),
    ]
    ax.legend(legend_handles, ["D = 1 (helpless)", "D = 5", "D = 9 (in control)"],
              loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3,
              fontsize=7.8, frameon=False, handletextpad=0.4, columnspacing=1.6)

    ax.set_xlim(0.5, 9.5)
    ax.set_ylim(0.5, 9.5)
    ax.set_xticks(range(1, 10))
    ax.set_yticks(range(1, 10))
    ax.set_xlabel("Valence")
    ax.set_ylabel("Arousal")
    ax.set_title(f"Corpus-wide VAD scatter (n = {len(pts):,} of {len(rows):,} scored posts)")

    out = OUT_DIR / "figure_05_vad_scatter.png"
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
# Figure 6 — Topic-by-VAD heatmap                                             #
# --------------------------------------------------------------------------- #

def figure_6(rows: list[dict]) -> Path:
    # (univ, topic_label) -> list of (V, A, D)
    bucket: dict[tuple[str, str], list[tuple[int, int, int]]] = defaultdict(list)
    for r in rows:
        if r.get("V") is None:
            continue
        label = r.get("topic_label") or ""
        if not label or label.lower() == "noise":
            continue
        univ = r.get("univ_code", "?")
        bucket[(univ, label)].append((r["V"], r["A"], r["D"]))

    items = [
        (univ, label, len(scores),
         np.mean([s[0] for s in scores]),
         np.mean([s[1] for s in scores]),
         np.mean([s[2] for s in scores]))
        for (univ, label), scores in bucket.items()
        if len(scores) >= MIN_POSTS_PER_TOPIC
    ]
    # Sort by mean V ascending (manuscript: "crisis cluster in upper-left").
    items.sort(key=lambda t: t[3])

    rownames = [f"{univ}  ·  {label[:46]}" for univ, label, _, _, _, _ in items]
    sizes = [n for _, _, n, _, _, _ in items]
    M = np.array([[v, a, d] for _, _, _, v, a, d in items])

    n_rows = len(items)
    fig_h = max(4.2, min(0.22 * n_rows + 1.6, 11))
    fig, (ax, ax_n) = plt.subplots(
        1, 2, figsize=(8.2, fig_h),
        gridspec_kw={"width_ratios": [4.2, 0.55], "wspace": 0.06},
    )

    im = ax.imshow(M, aspect="auto", cmap="RdYlBu_r", vmin=1, vmax=9)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["Valence", "Arousal", "Dominance"])
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(rownames, fontsize=7.2)
    ax.tick_params(axis="x", which="both", length=0)
    ax.tick_params(axis="y", which="both", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    # Annotate each cell with the mean.
    for i in range(n_rows):
        for j in range(3):
            v = M[i, j]
            ax.text(j, i, f"{v:.1f}", ha="center", va="center",
                    fontsize=7.0,
                    color="white" if (v <= 3.2 or v >= 6.8) else "#222")
    ax.set_title(f"Topic-by-VAD heatmap (n = {n_rows} topics with ≥ {MIN_POSTS_PER_TOPIC} posts; sorted by mean Valence)")

    # Column-bar of post counts.
    ax_n.barh(range(n_rows), sizes, color="#9aa0a8", height=0.72)
    ax_n.set_yticks([])
    ax_n.set_xticks([])
    ax_n.invert_yaxis()
    ax_n.set_title("posts", fontsize=8)
    for spine in ax_n.spines.values():
        spine.set_visible(False)
    for i, s in enumerate(sizes):
        ax_n.text(s, i, f" {s:,}", va="center", fontsize=6.8, color="#444")

    # Heatmap colorbar.
    cb = fig.colorbar(im, ax=[ax, ax_n], fraction=0.022, pad=0.02)
    cb.set_label("Dimension value (1 — 9)", fontsize=8.5)
    cb.ax.tick_params(labelsize=7.5)
    cb.outline.set_linewidth(0.4)

    # imshow places row 0 (lowest V, sorted ascending) at top — matches manuscript
    # caption "crisis quadrant clusters in the upper-left". No heatmap inversion.

    out = OUT_DIR / "figure_06_topic_heatmap.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def main() -> None:
    rows = load_all_vad()
    print(f"loaded {len(rows):,} VAD-scored rows from {VAD_DIR}")
    if not rows:
        raise SystemExit("no VAD rows found — run vad_scoring first")

    f5 = figure_5(rows)
    print(f"wrote {f5.relative_to(ROOT)}")
    f6 = figure_6(rows)
    print(f"wrote {f6.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
