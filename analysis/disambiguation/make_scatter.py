"""Scatter plot of pairwise structural ambiguity: six-field metric (x) vs
extended nine-dimension metric (y), over all pairs among the 70 enriched
resources. Points below the diagonal moved apart under enrichment.

Run:  python analysis/disambiguation/make_scatter.py
Output: analysis/disambiguation/output/fig_scatter.{pdf,png}
"""

from __future__ import annotations

import sys
from pathlib import Path
import itertools

import matplotlib.pyplot as plt
import matplotlib as mpl

# Match the LaTeX paper: serif font (Times-like), similar sizing to the
# tikz/pgfplots figures.
mpl.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "axes.linewidth": 0.6,
})

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "src").is_dir())
sys.path.insert(0, str(ROOT))

from src import loader as ord_loader                  # noqa: E402
from src.adversarial import preselect            # noqa: E402
from analysis.disambiguation import extended_metric as em  # noqa: E402

OUT = Path(__file__).resolve().parent / "output"
GT_TYPES = preselect.GROUND_TRUTH_TYPES
HIGH = 0.50


def _is_enriched(r: dict) -> bool:
    return bool(r.get("capabilities") or r.get("partOfGroups") or r.get("useCases"))


def main() -> None:
    resources = ord_loader.load_landscape(state="enriched")
    scored = [r for r in resources
              if (r.get("_rtype") or r.get("type")) != "entityType"]
    et_idf = preselect._et_idf(scored)
    tfidf = preselect._build_tfidf_index(scored)
    uc_tfidf = em.build_usecase_tfidf(scored)

    enr = [r for r in scored
           if (r.get("_rtype") or r.get("type")) in GT_TYPES and _is_enriched(r)]
    print(f"enriched resources: {len(enr)}")

    xs, ys = [], []
    for a, b in itertools.combinations(enr, 2):
        so, _ = em.pairwise_original(a, b, et_idf, tfidf)
        se, _ = em.pairwise_extended(a, b, et_idf, tfidf, uc_tfidf)
        xs.append(so)
        ys.append(se)
    print(f"pairs: {len(xs)}")

    fig, ax = plt.subplots(figsize=(3.4, 3.2))
    # diagonal (no change)
    ax.plot([0, 0.8], [0, 0.8], color="black", lw=0.6, ls="--", zorder=1)
    # points, coloured by whether they were HIGH-tier originally
    high_x = [x for x, y in zip(xs, ys) if x >= HIGH]
    high_y = [y for x, y in zip(xs, ys) if x >= HIGH]
    low_x = [x for x, y in zip(xs, ys) if x < HIGH]
    low_y = [y for x, y in zip(xs, ys) if x < HIGH]
    ax.scatter(low_x, low_y, s=6, c="#86B6EF", alpha=0.5, lw=0, zorder=2,
               label=f"below HIGH ($n{{=}}{len(low_x)}$)")
    ax.scatter(high_x, high_y, s=10, c="#1C5CAB", alpha=0.8, lw=0, zorder=3,
               label=f"HIGH-tier ($n{{=}}{len(high_x)}$)")
    ax.axvline(HIGH, color="0.6", lw=0.4, ls=":", zorder=1)

    ax.set_xlabel("Six-field ambiguity", fontsize=8)
    ax.set_ylabel("Extended ambiguity", fontsize=8)
    ax.set_xlim(0, 0.8)
    ax.set_ylim(0, 0.8)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=6, loc="upper left", frameon=False)
    ax.set_aspect("equal")
    fig.tight_layout()

    for ext in ("pdf", "png"):
        p = OUT / f"fig_scatter.{ext}"
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
