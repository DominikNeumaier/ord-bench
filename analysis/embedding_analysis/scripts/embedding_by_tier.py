"""Boxplot: embedding cosine distribution by similarity tier.

Uses the pairwise.csv already in analysis/embedding_analysis/ (no API calls).
Tier boundaries from src/adversarial/preselect.py:
  HIGH   0.50 – 0.75
  MEDIUM  0.25 – 0.50
  LOW     0.10 – 0.25
  NONE  < 0.10

Output: analysis/embedding_analysis/embedding_by_tier.pdf/.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

OUT = Path(__file__).resolve().parent.parent / "output"

df = pd.read_csv(OUT / "pairwise.csv")

# Assign tiers
def tier(s):
    if s >= 0.50: return "HIGH"
    if s >= 0.25: return "MEDIUM"
    if s >= 0.10: return "LOW"
    return "NONE"

df["tier"] = df["structural_sim"].apply(tier)

order = ["HIGH", "MEDIUM", "LOW", "NONE"]
labels = ["HIGH\n(0.50–0.75)", "MEDIUM\n(0.25–0.50)", "LOW\n(0.10–0.25)", "NONE\n(< 0.10)"]
colors = ["#d62728", "#ff7f0e", "#2ca02c", "#aec7e8"]

groups = [df.loc[df["tier"] == t, "embedding_cos"].values for t in order]
counts = [len(g) for g in groups]

fig, ax = plt.subplots(figsize=(6, 4))

bp = ax.boxplot(
    groups,
    patch_artist=True,
    medianprops=dict(color="white", linewidth=2),
    whiskerprops=dict(linewidth=1.2),
    capprops=dict(linewidth=1.2),
    flierprops=dict(marker=".", markersize=2, alpha=0.3, linestyle="none"),
    widths=0.55,
)

for patch, color in zip(bp["boxes"], colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.85)

ax.set_xticks(range(1, 5))
ax.set_xticklabels(
    [f"{l}\n(n={c:,})" for l, c in zip(labels, counts)],
    fontsize=8,
)
ax.set_ylabel("embedding cosine", fontsize=9)
ax.set_xlabel("structural ambiguity tier", fontsize=9)
ax.set_ylim(0, 1.05)
ax.yaxis.grid(True, linestyle="--", alpha=0.5)
ax.set_axisbelow(True)

# Annotate medians
for i, g in enumerate(groups):
    med = np.median(g)
    ax.text(i + 1, med + 0.025, f"{med:.2f}", ha="center", va="bottom",
            fontsize=7.5, fontweight="bold", color="white",
            bbox=dict(boxstyle="round,pad=0.15", fc=colors[i], ec="none", alpha=0.85))

fig.tight_layout()
for ext in ("pdf", "png"):
    fig.savefig(OUT / f"embedding_by_tier.{ext}", dpi=180, bbox_inches="tight")
print("Saved to", OUT / "embedding_by_tier.pdf")
