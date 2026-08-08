"""Generate the five evaluation figures consumed by the thesis paper.

Outputs go to Paper/figures/ as PDF (vector, IEEE-friendly).

Figures:
  fig1_cost_vs_accuracy.pdf    - DT cost-vs-Top1 scatter (log-x tokens)
  fig2_refusal_vs_top1.pdf     - RT refusal-rate vs Top-1 trade-off
  fig3_heatmap_method_process.pdf - DT P@1 heatmap (5 methods x 12 processes)
  fig4_latency_boxplot.pdf     - DT per-case wall_s distribution per method
  fig5_coverage_by_mode.pdf    - RT planner coverage (full/partial/none) per expected mode

Style: serif fonts, mostly monochrome (black/grey), one accent grey for in-bold
points (Method D), 6x4 in single-column, 7x4 for wider plots.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
PAPER_FIG = ROOT.parent / "Paper" / "figures"
PAPER_FIG.mkdir(parents=True, exist_ok=True)

# Common style — IEEE-friendly: Times-like serif, black-and-grey, no flashy colors.
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 9,
    "axes.labelsize": 9,
    "axes.titlesize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "axes.linewidth": 0.6,
    "lines.linewidth": 1.0,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
})

METHODS = ["A", "B", "C", "D", "E"]
# Grey palette: D in solid black (it's the protagonist), others in graded grey.
COLORS = {"A": "#888888", "B": "#666666", "C": "#999999", "D": "#000000", "E": "#aaaaaa"}
MARKERS = {"A": "o", "B": "s", "C": "^", "D": "D", "E": "v"}


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ─────────────────────────────────────────────────────────────────────────────
# FIG 1 — Cost-vs-Accuracy scatter (DT)
# ─────────────────────────────────────────────────────────────────────────────
def fig1_cost_vs_accuracy() -> None:
    rows = read_csv(RESULTS / "design-time" / "summary.csv")
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    for row in rows:
        m = row["method"]
        tokens_per_case = float(row["avg_tokens_per_case"])
        p_at_1 = float(row["P@1"])
        ax.scatter(
            tokens_per_case,
            p_at_1,
            s=70,
            marker=MARKERS[m],
            facecolor=COLORS[m] if m == "D" else "white",
            edgecolor=COLORS[m],
            linewidth=1.0,
            zorder=3,
        )
        # Label placement: offset based on method to avoid overlap.
        # B and C sit very close in x (both ~2.4k tokens), so we push B's
        # label right and up, C's label right and slightly down.
        dx, dy, ha = 1.10, 0.012, "left"
        if m == "A":
            dx, dy, ha = 1.10, -0.025, "left"
        if m == "B":
            dx, dy, ha = 1.18, 0.020, "left"
        if m == "C":
            dx, dy, ha = 1.18, -0.020, "left"
        if m == "D":
            dx, dy, ha = 1.10, 0.015, "left"
        if m == "E":
            dx, dy, ha = 1.10, -0.030, "left"
        ax.annotate(
            m,
            (tokens_per_case * dx, p_at_1 + dy),
            fontsize=8.5,
            ha=ha,
            fontweight="bold" if m == "D" else "normal",
        )
    ax.set_xscale("log")
    ax.set_xlabel("Average tokens per case (log scale)")
    ax.set_ylabel("Top-1 Accuracy")
    ax.set_ylim(0.30, 0.95)
    # Show more x-axis ticks so the reader can read off intermediate token counts.
    from matplotlib.ticker import LogLocator, FuncFormatter
    ax.xaxis.set_major_locator(LogLocator(base=10.0, numticks=10))
    ax.xaxis.set_minor_locator(LogLocator(base=10.0, subs=tuple(range(2, 10)), numticks=10))
    ax.xaxis.set_minor_formatter(FuncFormatter(
        lambda v, _: f"{int(v/1000)}k" if v in (2000, 5000, 20000) else ""
    ))
    ax.tick_params(axis="x", which="minor", labelsize=7)
    ax.grid(True, which="both", linestyle=":", linewidth=0.4, color="0.7", zorder=0)
    ax.set_axisbelow(True)
    fig.savefig(PAPER_FIG / "fig1_cost_vs_accuracy.pdf")
    plt.close(fig)
    print("  ✓ fig1_cost_vs_accuracy.pdf")


# ─────────────────────────────────────────────────────────────────────────────
# FIG 2 — Refusal vs Top-1 trade-off (RT, enriched state)
# ─────────────────────────────────────────────────────────────────────────────
def fig2_refusal_vs_top1() -> None:
    # In-scope Top-1: weighted average over the three in-scope modes per method,
    # using the enriched (x1) condition only.
    insc_top1 = {}
    case_counts = {}
    for mode in ["skill_guided", "skill_adjusted", "dynamic"]:
        rows = read_csv(RESULTS / "runtime" / mode / "summary.csv")
        for row in rows:
            if row["state"] != "enriched":
                continue
            m = row["method"]
            n = int(row["cases"])
            t1 = float(row["Top-1"])
            insc_top1[m] = insc_top1.get(m, 0.0) + t1 * n
            case_counts[m] = case_counts.get(m, 0) + n
    for m in METHODS:
        insc_top1[m] = insc_top1[m] / case_counts[m]

    oos_rows = read_csv(RESULTS / "runtime" / "out_of_scope" / "summary.csv")
    refusal = {row["method"]: float(row["Refusal-Rate"])
               for row in oos_rows if row["state"] == "enriched"}

    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    for m in METHODS:
        x = refusal[m]
        y = insc_top1[m]
        ax.scatter(
            x, y,
            s=70,
            marker=MARKERS[m],
            facecolor=COLORS[m] if m == "D" else "white",
            edgecolor=COLORS[m],
            linewidth=1.0,
            zorder=3,
        )
        # Per-point label offsets to keep them legible.
        offsets = {
            "A": (0.025, 0.005),
            "B": (0.025, 0.012),
            "C": (0.025, -0.025),
            "D": (0.025, 0.005),
            "E": (-0.025, 0.012),
        }
        dx, dy = offsets[m]
        ax.annotate(
            m,
            (x + dx, y + dy),
            fontsize=8.5,
            ha="right" if dx < 0 else "left",
            fontweight="bold" if m == "D" else "normal",
        )
    # Ideal corner annotation — top-right.
    ax.annotate(
        "ideal", xy=(0.97, 0.97), xytext=(0.97, 0.93),
        fontsize=7.5, color="0.5", ha="right", style="italic",
        xycoords="axes fraction", textcoords="axes fraction",
    )
    ax.set_xlabel("Refusal-Rate on out-of-scope cases")
    ax.set_ylabel("Top-1 Accuracy on in-scope cases")
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(0.40, 0.85)
    ax.grid(True, linestyle=":", linewidth=0.4, color="0.7", zorder=0)
    ax.set_axisbelow(True)
    fig.savefig(PAPER_FIG / "fig2_refusal_vs_top1.pdf")
    plt.close(fig)
    print("  ✓ fig2_refusal_vs_top1.pdf")


# ─────────────────────────────────────────────────────────────────────────────
# FIG 3 — Method × Process heatmap (DT, in-scope only, P@1)
# ─────────────────────────────────────────────────────────────────────────────
def fig3_heatmap_method_process() -> None:
    rows = read_csv(RESULTS / "design-time" / "by_process.csv")
    # Build matrix: rows = methods, cols = in-scope processes
    by_process: dict[str, dict[str, float]] = {}
    for row in rows:
        proc = row["process"]
        m = row["method"]
        p1 = row.get("P@1", "")
        if p1 == "":  # OOS row (no P@1)
            continue
        by_process.setdefault(proc, {})[m] = float(p1)

    processes = sorted(by_process.keys())
    matrix = np.array([[by_process[p].get(m, np.nan) for p in processes] for m in METHODS])

    # Short labels: strip suffix, abbreviate notation marker
    def short(name: str) -> str:
        base = name.replace(".bpmn", "").replace(".cmmn", "")
        suffix = " (B)" if name.endswith(".bpmn") else " (C)"
        # Strip underscores
        return base.replace("_", " ") + suffix

    proc_labels = [short(p) for p in processes]

    fig, ax = plt.subplots(figsize=(7.0, 2.4))
    im = ax.imshow(matrix, cmap="Greys", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(processes)))
    ax.set_xticklabels(proc_labels, rotation=40, ha="right", fontsize=7.5)
    ax.set_yticks(range(len(METHODS)))
    ax.set_yticklabels(METHODS)
    # Cell annotations
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix[i, j]
            if np.isnan(v):
                continue
            color = "white" if v > 0.55 else "black"
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    fontsize=6.5, color=color)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.015)
    cb.set_label("P@1", fontsize=8)
    cb.ax.tick_params(labelsize=7)
    fig.savefig(PAPER_FIG / "fig3_heatmap_method_process.pdf")
    plt.close(fig)
    print("  ✓ fig3_heatmap_method_process.pdf")


# ─────────────────────────────────────────────────────────────────────────────
# FIG 4 — Per-case wall-clock distribution per method (DT)
# ─────────────────────────────────────────────────────────────────────────────
def fig4_latency_boxplot() -> None:
    base = RESULTS / "design-time" / "traces"
    data = {m: [] for m in METHODS}
    for m in METHODS:
        for f in (base / m).glob("*.json"):
            try:
                obj = json.loads(f.read_text(encoding="utf-8"))
                w = obj.get("wall_s")
                if isinstance(w, (int, float)) and w > 0:
                    data[m].append(float(w))
            except Exception:
                continue

    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    positions = list(range(1, len(METHODS) + 1))
    bp = ax.boxplot(
        [data[m] for m in METHODS],
        positions=positions,
        widths=0.55,
        patch_artist=True,
        showfliers=True,
        flierprops=dict(marker=".", markersize=3, markerfacecolor="0.5",
                        markeredgecolor="0.5"),
        medianprops=dict(color="black", linewidth=1.0),
        whiskerprops=dict(linewidth=0.6),
        capprops=dict(linewidth=0.6),
        boxprops=dict(linewidth=0.6),
    )
    for i, m in enumerate(METHODS):
        bp["boxes"][i].set_facecolor("0.92" if m != "D" else "0.75")
        bp["boxes"][i].set_edgecolor("black")
    ax.set_xticks(positions)
    ax.set_xticklabels(METHODS)
    ax.set_ylabel("Runtime per case (s, log scale)")
    ax.set_yscale("log")
    ax.grid(True, axis="y", which="both", linestyle=":",
            linewidth=0.4, color="0.7", zorder=0)
    ax.set_axisbelow(True)
    fig.savefig(PAPER_FIG / "fig4_latency_boxplot.pdf")
    plt.close(fig)
    print(f"  ✓ fig4_latency_boxplot.pdf "
          f"(n={[len(data[m]) for m in METHODS]})")


# ─────────────────────────────────────────────────────────────────────────────
# FIG 5 — Planner coverage verdict per expected mode (RT)
# ─────────────────────────────────────────────────────────────────────────────
def fig5_coverage_by_mode() -> None:
    # Aggregate over methods + states (the planner's verdict is method-independent,
    # but we collect once per trace and dedupe by case_id to avoid 10x overcount).
    by_mode_cov: dict[str, Counter] = defaultdict(Counter)
    seen: dict[str, set] = defaultdict(set)
    for mode_dir in ["skill_guided", "skill_adjusted", "dynamic", "out_of_scope"]:
        base = RESULTS / "runtime" / mode_dir / "traces"
        for cond_dir in base.iterdir():
            if not cond_dir.is_dir():
                continue
            # Only use one method's traces per (mode, case) to dedupe
            # — use A0 since A is fastest.
            if cond_dir.name != "A0":
                continue
            for f in cond_dir.glob("*.json"):
                try:
                    obj = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                cid = obj.get("case_id", f.stem)
                expected = obj.get("mode_expected") or mode_dir
                plan = obj.get("plan", {})
                cov = plan.get("coverage", "unknown")
                if cid in seen[expected]:
                    continue
                seen[expected].add(cid)
                by_mode_cov[expected][cov] += 1

    # Render as stacked horizontal bars
    expected_modes = ["skill_guided", "skill_adjusted", "dynamic", "out_of_scope"]
    labels = ["Skill-Guided", "Skill-Adjusted", "Dynamic", "Out-of-Scope"]
    cov_order = ["full", "partial", "none"]
    cov_colors = {"full": "0.15", "partial": "0.55", "none": "0.85"}
    cov_pretty = {"full": "full cover", "partial": "partial cover", "none": "no match"}

    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    y_positions = np.arange(len(expected_modes))
    for idx, mode in enumerate(expected_modes):
        total = sum(by_mode_cov[mode].values()) or 1
        left = 0.0
        for cov in cov_order:
            v = by_mode_cov[mode].get(cov, 0) / total
            ax.barh(y_positions[idx], v, left=left,
                    color=cov_colors[cov], edgecolor="black", linewidth=0.4)
            if v > 0.06:
                ax.text(left + v / 2, y_positions[idx], f"{v:.2f}",
                        ha="center", va="center", fontsize=7,
                        color="white" if cov == "full" else "black")
            left += v
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("Share of cases by planner coverage verdict")
    # Custom legend
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=cov_colors[c], edgecolor="black",
                     label=cov_pretty[c], linewidth=0.4) for c in cov_order]
    ax.legend(handles=handles, loc="lower right", ncol=3, frameon=False,
              bbox_to_anchor=(1.0, -0.45), fontsize=7.5,
              handlelength=1.2, handletextpad=0.5, columnspacing=1.0)
    fig.savefig(PAPER_FIG / "fig5_coverage_by_mode.pdf")
    plt.close(fig)
    print("  ✓ fig5_coverage_by_mode.pdf")


if __name__ == "__main__":
    print(f"Writing figures to {PAPER_FIG}")
    fig1_cost_vs_accuracy()
    fig2_refusal_vs_top1()
    fig3_heatmap_method_process()
    fig4_latency_boxplot()
    fig5_coverage_by_mode()
    print("Done.")
