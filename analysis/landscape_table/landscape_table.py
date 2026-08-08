"""Reproduce the landscape composition table (Paper I, Table 4).

Counts, per namespace, the resources of each type (apiResource / agent /
dataProduct) and the number that are ground-truth eligible — i.e. that reached
the required neighbourhood (HIGH>=3, MEDIUM>=5, LOW>=5) under the benchmark's
full similarity metric.

Type counts are read from the clean landscape (data/landscape/systems/).
GT eligibility is read from the pre-computed ambiguity report
(data/ambiguity/landscape_ambiguity_report.json, field ground_truth_eligible),
which is produced by src/adversarial/preselect.py on the final corpus.

Domain labels are display-only (they describe each system for the paper; they
are not stored in the ORD documents).

It also prints a neighbourhood summary (Paper I, R1 text): the average number of
HIGH / MEDIUM / LOW-tier neighbours per resource, the resource-type distribution,
and the ground-truth-eligible count — all from the ambiguity report (full metric,
incl. the TF-IDF text score).

Run:  python3 analysis/landscape_table/landscape_table.py

No API calls. Reads only the on-disk landscape and ambiguity report.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "src").is_dir())
sys.path.insert(0, str(ROOT))

from src import loader                                    # noqa: E402

AMBIGUITY_REPORT = ROOT / "data" / "ambiguity" / "landscape_ambiguity_report.json"

# Display order + domain labels (paper Table 4). Not stored in the data.
NAMESPACES = [
    ("sap.s4",      "ERP, Finance"),
    ("sap.sf",      "HR"),
    ("sap.ariba",   "Procurement"),
    ("sap.crm",     "Sales, Customer"),
    ("sap.ehs",     "Safety, Env."),
    ("corp.itsm",   "IT Service Mgmt"),
    ("my.mes",      "Mfg. Execution"),
    ("workday.hcm", "HR (non-SAP)"),
    ("emarsys.cx",  "Marketing, CX"),
    ("siemens.plm", "Prod. Lifecycle"),
]

TYPE_KEYS = ["apiResource", "agent", "dataProduct"]


def type_counts() -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in loader.load_landscape("clean"):
        rt = r.get("_rtype") or r.get("type")
        if rt == "entityType":
            continue
        counts[r.get("namespace")][rt] += 1
    return counts


def gt_counts() -> dict[str, int]:
    report = json.loads(AMBIGUITY_REPORT.read_text())
    gt: dict[str, int] = defaultdict(int)
    for r in report["resources"]:
        if r.get("ground_truth_eligible"):
            ns = r["ordId"].split(":")[0]
            gt[ns] += 1
    return gt


def neighbourhood_summary() -> None:
    """Avg. neighbours per tier, type distribution, and GT-eligible count —
    all from the ambiguity report (full metric, incl. TF-IDF text). Also
    recomputes the mean top-5 ambiguity under both the full metric and the
    generation-time metric (_fast_sim, text score = 0, the one Fig. 3 plots),
    for the full-vs-fast comparison in the paper."""
    report = json.loads(AMBIGUITY_REPORT.read_text())
    res = report["resources"]
    n = len(res)
    avg_high = sum(r["high_neighbors"] for r in res) / n
    avg_med = sum(r["medium_neighbors"] for r in res) / n
    avg_low = sum(r["low_neighbors"] for r in res) / n
    types = {}
    for r in res:
        types[r["type"]] = types.get(r["type"], 0) + 1
    gt = sum(1 for r in res if r.get("ground_truth_eligible"))

    # mean top-5 ambiguity under full vs generation-time (text=0) metric
    from src.adversarial import preselect as ps
    scored = [r for r in loader.load_landscape("clean")
              if (r.get("_rtype") or r.get("type")) != "entityType"]
    idf = ps._et_idf(scored)
    tfidf = ps._build_tfidf_index(scored)

    def mean_top5(use_tfidf: bool) -> float:
        tf = tfidf if use_tfidf else {}
        per = []
        for i, a in enumerate(scored):
            sims = [ps._pairwise_sim(a, b, idf, tf)[0]
                    for j, b in enumerate(scored) if i != j]
            top = sorted(sims, reverse=True)[:5]
            per.append(sum(top) / len(top))
        return sum(per) / len(per)

    mt5_full = mean_top5(True)
    mt5_fast = mean_top5(False)

    print("Neighbourhood summary (full metric, incl. TF-IDF text)")
    print(f"  resources              : {n}")
    print(f"  avg HIGH-tier neighbours   : {avg_high:.2f}")
    print(f"  avg MEDIUM-tier neighbours : {avg_med:.1f}")
    print(f"  avg LOW-tier neighbours    : {avg_low:.1f}")
    print(f"  mean top-5 ambiguity (full metric)          : {mt5_full:.2f}")
    print(f"  mean top-5 ambiguity (generation-time, Fig3): {mt5_fast:.2f}")
    print("  type distribution      : " + ", ".join(
        f"{100 * c / n:.0f}% {t}" for t, c in sorted(types.items())))
    print(f"  ground-truth eligible  : {gt} of {n}")


def main() -> None:
    tc = type_counts()
    gt = gt_counts()

    hdr = f"{'Namespace':14} {'Domain':17} {'API':>3} {'Agt':>3} {'DP':>3} {'Tot':>4} {'GT':>3}"
    print(hdr)
    print("-" * len(hdr))
    tot = {k: 0 for k in TYPE_KEYS}
    tot_all = tot_gt = 0
    for ns, domain in NAMESPACES:
        a = tc[ns].get("apiResource", 0)
        ag = tc[ns].get("agent", 0)
        dp = tc[ns].get("dataProduct", 0)
        n = a + ag + dp
        g = gt.get(ns, 0)
        tot["apiResource"] += a
        tot["agent"] += ag
        tot["dataProduct"] += dp
        tot_all += n
        tot_gt += g
        print(f"{ns:14} {domain:17} {a:>3} {ag:>3} {dp:>3} {n:>4} {g:>3}")
    print("-" * len(hdr))
    print(f"{'Total':14} {'':17} {tot['apiResource']:>3} {tot['agent']:>3} "
          f"{tot['dataProduct']:>3} {tot_all:>4} {tot_gt:>3}")
    print()
    neighbourhood_summary()


if __name__ == "__main__":
    main()
