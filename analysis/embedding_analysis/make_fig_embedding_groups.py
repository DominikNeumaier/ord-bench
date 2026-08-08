"""Reproduce Figure 6 (embedding cosine: clean vs enriched text, by group).

Reads analysis/disambiguation/output/disambiguation_report.json (produced by
run_disambiguation.py) and renders the three-group bar chart the paper shows:

  All enriched (n=2415)  — both resources in the pair carry semantic fields
  Prev. HIGH   (n=85)    — the subset that was HIGH-tier under the structural metric
  Mixed        (n=14210) — only one resource in the pair is enriched

Each group shows mean embedding cosine on the clean Method-A text (title +
shortDescription + description) versus the enriched text (+ the four semantic
fields). Unlike the structural metric (Fig. 4), embedding cosine rises in every
group once semantic text is added.

The report fields used:
  embedding             -> All enriched
  embedding_high_subset -> Prev. HIGH
  embedding_mixed_pairs -> Mixed

Run:  python3 analysis/embedding_analysis/make_fig_embedding_groups.py
Output: analysis/embedding_analysis/embedding_clean_vs_enriched.{pdf,png}

No API calls. Reads only the disambiguation report.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "src").is_dir())
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPORT = ROOT / "analysis" / "disambiguation" / "output" / "disambiguation_report.json"
OUT = Path(__file__).resolve().parent

INK_CLEAN = "#c7c7c7"     # grey  — clean text
INK_ENRICHED = "#ffffff"  # white — enriched text (black edge)
GRID = "#d9d9d9"
TEXT = "#333333"

plt.rcParams.update({
    "font.family": "serif", "font.size": 9,
    "axes.edgecolor": "#888888", "axes.linewidth": 0.6,
    "text.color": TEXT, "axes.labelcolor": TEXT,
    "xtick.color": TEXT, "ytick.color": TEXT,
})


def main() -> None:
    report = json.loads(REPORT.read_text())
    avg = report["avg_similarity_enriched_pairs"]
    groups = [
        ("All enriched", avg["embedding"]),
        ("Prev. HIGH", avg["embedding_high_subset"]),
        ("Mixed", avg["embedding_mixed_pairs"]),
    ]

    labels = [f"{name}\n(n={g['n']})" for name, g in groups]
    clean = [g["mean_original"] for _, g in groups]
    enriched = [g["mean_extended"] for _, g in groups]

    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    x = np.arange(len(groups))
    w = 0.38
    b1 = ax.bar(x - w / 2, clean, w, color=INK_CLEAN, edgecolor="#555555",
                linewidth=0.6, label="Clean text", zorder=3)
    b2 = ax.bar(x + w / 2, enriched, w, color=INK_ENRICHED, edgecolor="#555555",
                linewidth=0.6, label="Enriched text", zorder=3)
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.008,
                    f"{b.get_height():.3f}", ha="center", va="bottom",
                    fontsize=7, color=TEXT)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Mean embedding cosine")
    ax.set_ylim(0, max(enriched) * 1.25)
    ax.grid(axis="y", color=GRID, linewidth=0.6, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper right")

    fig.tight_layout()
    for ext in ("pdf", "png"):
        p = OUT / f"embedding_clean_vs_enriched.{ext}"
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print(f"wrote {p}")
    plt.close(fig)

    # echo the numbers for traceability
    print()
    for name, g in groups:
        print(f"  {name:13} n={g['n']:>6}  clean={g['mean_original']:.3f}  "
              f"enriched={g['mean_extended']:.3f}  ({g['pct_change']:+.1f}%)")


if __name__ == "__main__":
    main()
