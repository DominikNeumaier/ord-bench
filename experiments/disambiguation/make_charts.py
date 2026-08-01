"""Charts for the disambiguation experiment.

Reads experiments/paper1/disambiguation/output/disambiguation_report.json and renders
two thesis-style figures (PDF + PNG) to the same output directory:

  fig_high_tier.pdf   — HIGH-tier neighbour count per resource, original metric
                        vs extended metric. Same tier and quantity as the
                        landscape-convergence figure (Fig. 4), so the two read
                        on one scale: generation ADDS confusables, the semantic
                        layer REMOVES them.

  fig_embedding.pdf   — counter-check: nearest-neighbour embedding cosine on the
                        clean Method-A text vs the enriched text. Shows the
                        embedding representation does NOT separate the pairs the
                        structural metric does — the mechanism behind A's flat/
                        negative enrichment response.

No API calls. Palette: two fixed categorical inks (blue = clean/original,
amber = enriched/extended), grey grid, per dataviz rules.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parent / "output"

# Fixed categorical inks — assigned by entity, not rank (dataviz non-negotiable).
INK_ORIGINAL = "#3b6fb0"   # blue  — original metric / clean text
INK_EXTENDED = "#d98c1f"   # amber — extended metric / enriched text
GRID = "#d9d9d9"
TEXT = "#333333"

plt.rcParams.update({
    "font.size": 9,
    "font.family": "serif",
    "axes.edgecolor": "#888888",
    "axes.linewidth": 0.6,
    "text.color": TEXT,
    "axes.labelcolor": TEXT,
    "xtick.color": TEXT,
    "ytick.color": TEXT,
})


def _load() -> dict:
    return json.loads((OUT / "disambiguation_report.json").read_text())


def fig_high_tier(report: dict) -> None:
    s_all = report["structural_all"]["summary"]
    s_enr = report["structural_enriched"]["summary"]

    fig, ax = plt.subplots(figsize=(4.6, 3.2))

    # 4 bars: two populations x {original, extended}, grouped by population
    groups = [
        (f"All resources\n(n={s_all['n_resources']})",
         s_all["avg_high_neighbors_original"], s_all["avg_high_neighbors_extended"]),
        (f"Enriched GT\n(n={s_enr['n_resources']})",
         s_enr["avg_high_neighbors_original"], s_enr["avg_high_neighbors_extended"]),
    ]
    x = np.arange(len(groups))
    w = 0.36
    orig_vals = [g[1] for g in groups]
    ext_vals = [g[2] for g in groups]

    b1 = ax.bar(x - w / 2, orig_vals, w, color=INK_ORIGINAL,
                label="Original metric (6 fields)", zorder=3)
    b2 = ax.bar(x + w / 2, ext_vals, w, color=INK_EXTENDED,
                label="Extended metric (+ semantic)", zorder=3)
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.05,
                    f"{b.get_height():.2f}", ha="center", va="bottom",
                    fontsize=8, color=TEXT)

    ax.set_xticks(x)
    ax.set_xticklabels([g[0] for g in groups])
    ax.set_ylabel("Avg. HIGH-tier neighbours\nper resource (sim $\\geq$ 0.50)")
    ax.set_ylim(0, max(orig_vals) * 1.25)
    ax.grid(axis="y", color=GRID, linewidth=0.6, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper right")

    fig.tight_layout()
    fig.savefig(OUT / "fig_high_tier.pdf", bbox_inches="tight")
    fig.savefig(OUT / "fig_high_tier.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / 'fig_high_tier.pdf'}")


def fig_embedding(report: dict) -> None:
    """Two slope panels on the SAME 2415 enriched pairs: structural metric
    (falls) vs embedding cosine (rises)."""
    a = report.get("avg_similarity_enriched_pairs")
    if not a:
        print("no avg_similarity_enriched_pairs — skipping fig_embedding")
        return
    s, e = a["structural"], a["embedding"]

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(6.0, 3.2))

    def slope(ax, before, after, title, ink):
        ax.plot([0, 1], [before, after], color=ink, linewidth=2, marker="o",
                markersize=6, zorder=3)
        ax.text(0, before, f" {before:.3f}", ha="right", va="center", fontsize=9, color=TEXT)
        ax.text(1, after, f"{after:.3f} ", ha="left", va="center", fontsize=9, color=TEXT)
        ax.set_xlim(-0.6, 1.6)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Clean", "Enriched"])
        ax.set_title(title, fontsize=9)
        ax.grid(axis="y", color=GRID, linewidth=0.6, zorder=0)
        ax.spines[["top", "right"]].set_visible(False)

    slope(axL, s["mean_original"], s["mean_extended"],
          f"Structural metric ({s['pct_change']:+.0f}%)", INK_ORIGINAL)
    axL.set_ylabel("Mean pairwise ambiguity")
    slope(axR, e["mean_original"], e["mean_extended"],
          f"Embedding cosine ({e['pct_change']:+.0f}%)", INK_EXTENDED)
    axR.set_ylabel("Mean cosine similarity")

    fig.suptitle(f"Same {a['n_pairs']} enriched pairs", fontsize=9, y=1.02)
    fig.tight_layout()
    fig.savefig(OUT / "fig_embedding.pdf", bbox_inches="tight")
    fig.savefig(OUT / "fig_embedding.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / 'fig_embedding.pdf'}")


def main():
    report = _load()
    fig_high_tier(report)
    fig_embedding(report)


if __name__ == "__main__":
    main()
