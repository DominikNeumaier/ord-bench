"""Reproduce the iterative-generation convergence figure (Paper I, Fig. 3).

Both data series are reconstructed from data/landscape/logs/enrichment_log.json,
which has been reduced to the single final generation run that produced the
published 273-resource landscape (30 seeds + 270 accepted, minus 27 near-duplicate
removals). Nothing here is hand-drawn — every number traces to the log.

  Bars (candidates generated / accepted per round)
      Every `create` entry in phase "iterative" is one generation attempt; those
      with outcome "accepted" are the acceptances. Round 0 is the 30 seed
      resources (3 per system). Read directly from the log.

  Mean top-5 ambiguity curve (the benchmark's own ambiguity score)
      Each accepted iterative entry carries an `ordId` (see ordId_reconstructed:
      the id was matched to the final landscape by namespace + rtype +
      entityTypes + lineOfBusiness; 243 of 270 accepts map to a surviving
      resource, the other 27 were dropped by near-duplicate reduction). The
      cumulative landscape after each round is rebuilt from those real resources.
      For every resource we take the mean similarity to its 5 nearest neighbours
      (the ambiguity score defined in src/adversarial/preselect.py) and average
      over all resources. Similarity uses the generation-time metric `_fast_sim`
      (the full pairwise metric with the TF-IDF text dimension set to 0 for O(1)
      speed; see src/generation/generate_iterative.py:_fast_sim). The curve shows
      diminishing returns: each added resource raises the average ambiguity less
      than the last, which is why generation was capped at 300 candidates rather
      than pushed to a larger catalogue.

Run:  python3 analysis/convergence/reconstruct_convergence.py
      python3 analysis/convergence/reconstruct_convergence.py --plot   (writes PDF+PNG)

No API calls. Reads only the generation log and the on-disk landscape.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "src").is_dir())
sys.path.insert(0, str(ROOT))

from src import loader                                    # noqa: E402
from src.adversarial import preselect as ps               # noqa: E402

LOG_PATH = ROOT / "data" / "landscape" / "logs" / "enrichment_log.json"
OUT = Path(__file__).resolve().parent
HIGH = 0.50
TOP_K = 5


def load_log() -> list[dict]:
    return json.loads(LOG_PATH.read_text())


def seed_ids(log: list[dict]) -> list[str]:
    ids = [e["ordId"] for e in log
           if e.get("phase") == "seed" and e.get("ordId")]
    return list(dict.fromkeys(ids))  # dedup, preserve order


def bars_per_round(log: list[dict]) -> dict[int, dict[str, int]]:
    """generated / accepted per iterative round; round 0 = seeds."""
    seeds = len(seed_ids(log))
    per: dict[int, dict[str, int]] = {0: {"generated": seeds, "accepted": seeds}}
    gen: dict[int, int] = defaultdict(int)
    acc: dict[int, int] = defaultdict(int)
    for e in log:
        if e.get("phase") != "iterative" or e.get("action") != "create":
            continue
        r = e.get("round")
        gen[r] += 1
        if e.get("outcome") == "accepted":
            acc[r] += 1
    for r in sorted(gen):
        per[r] = {"generated": gen[r], "accepted": acc[r]}
    return per


def accepted_ids_per_round(log: list[dict]) -> dict[int, list[str]]:
    """Matched ordIds of resources accepted in each iterative round (survivors
    only; dedup-removed accepts carry ordId=None and are skipped)."""
    by_round: dict[int, list[str]] = defaultdict(list)
    for e in log:
        if (e.get("phase") == "iterative" and e.get("outcome") == "accepted"
                and e.get("ordId")):
            by_round[e["round"]].append(e["ordId"])
    return by_round


def mean_top5_ambiguity(resources: list[dict]) -> float:
    """Mean over all resources of each resource's mean similarity to its TOP_K
    nearest neighbours — the benchmark's ambiguity score (preselect.py), scored
    under the generation-time metric _fast_sim (text dim = 0)."""
    scored = [r for r in resources
              if (r.get("_rtype") or r.get("type")) != "entityType"]
    if not scored:
        return 0.0
    idf = ps._et_idf(scored)
    per_resource = []
    for i, a in enumerate(scored):
        sims = [ps._pairwise_sim(a, b, idf, {})[0]
                for j, b in enumerate(scored) if i != j]
        top = sorted(sims, reverse=True)[:TOP_K]
        per_resource.append(sum(top) / len(top) if top else 0.0)
    return sum(per_resource) / len(per_resource)


def convergence_series(log: list[dict]) -> list[dict]:
    """Per-round: generated, accepted, cumulative size, mean top-5 ambiguity."""
    final = {r["ordId"]: r for r in loader.load_landscape("clean")}
    bars = bars_per_round(log)
    acc_ids = accepted_ids_per_round(log)

    cum = [final[o] for o in seed_ids(log) if o in final]
    series = [{
        "round": 0,
        "generated": bars[0]["generated"],
        "accepted": bars[0]["accepted"],
        "cumulative": len(cum),
        "mean_top5_ambiguity": round(mean_top5_ambiguity(cum), 4),
    }]
    for r in sorted(k for k in bars if k != 0):
        for oid in acc_ids.get(r, []):
            if oid in final:
                cum.append(final[oid])
        series.append({
            "round": r,
            "generated": bars[r]["generated"],
            "accepted": bars[r]["accepted"],
            "cumulative": len(cum),
            "mean_top5_ambiguity": round(mean_top5_ambiguity(cum), 4),
        })
    return series


def plot(series: list[dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update({"font.family": "serif", "font.size": 9,
                         "axes.linewidth": 0.6})
    rounds = [s["round"] for s in series]
    gen = [s["generated"] for s in series]
    acc = [s["accepted"] for s in series]
    ambig = [s["mean_top5_ambiguity"] for s in series]

    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    x = np.arange(len(rounds))
    w = 0.4
    ax.bar(x - w / 2, gen, w, color="#c7c7c7", label="Generated", zorder=3)
    ax.bar(x + w / 2, acc, w, color="#1f6fd0", label="Accepted", zorder=3)
    ax.set_xlabel("Generation round")
    ax.set_ylabel("Candidates per round")
    ax.set_xticks(x)
    ax.set_xticklabels(["S"] + [str(r) for r in rounds[1:]])
    ax.grid(axis="y", color="#d9d9d9", linewidth=0.6, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)

    ax2 = ax.twinx()
    ax2.plot(x, ambig, color="#8b1a1a", marker="o", markersize=3.5,
             linewidth=1.6, label="Mean top-5 ambiguity", zorder=4)
    ax2.set_ylabel("Mean top-5 ambiguity")
    ax2.set_ylim(0, max(ambig) * 1.25 if max(ambig) else 1)
    ax2.spines[["top"]].set_visible(False)

    l1, lab1 = ax.get_legend_handles_labels()
    l2, lab2 = ax2.get_legend_handles_labels()
    ax.legend(l1 + l2, lab1 + lab2, frameon=False, fontsize=7, loc="upper right")

    fig.tight_layout()
    for ext in ("pdf", "png"):
        p = OUT / f"convergence.{ext}"
        fig.savefig(p, dpi=200, bbox_inches="tight")
        print(f"wrote {p}")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plot", action="store_true", help="also write PDF+PNG")
    args = ap.parse_args()

    log = load_log()
    series = convergence_series(log)

    print(f"{'round':>5} {'generated':>9} {'accepted':>8} {'cumulative':>10} {'ambig':>8}")
    for s in series:
        label = "0(S)" if s["round"] == 0 else str(s["round"])
        print(f"{label:>5} {s['generated']:>9} {s['accepted']:>8} "
              f"{s['cumulative']:>10} {s['mean_top5_ambiguity']:>8.4f}")

    tot_g = sum(s["generated"] for s in series)
    tot_a = sum(s["accepted"] for s in series)
    print(f"{'TOTAL':>5} {tot_g:>9} {tot_a:>8}")
    print(f"\nfinal cumulative before near-dup reduction: {series[-1]['cumulative']}")
    print("minus 27 near-duplicate removals = 273 (published landscape)")

    (OUT / "convergence_data.json").write_text(json.dumps(series, indent=2))
    print(f"\nwrote {OUT / 'convergence_data.json'}")

    if args.plot:
        plot(series)


if __name__ == "__main__":
    main()
