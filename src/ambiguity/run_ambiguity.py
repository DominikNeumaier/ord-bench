"""Standalone runner for landscape ambiguity scoring.

Usage:
    python data/ambiguity/run_ambiguity.py
    python data/ambiguity/run_ambiguity.py --output data/ambiguity/landscape_ambiguity_report.json
    python data/ambiguity/run_ambiguity.py --top-k 10 --min-score 0.30
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root or from this directory
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from src import loader as ord_loader
from src.adversarial.preselect import compute_landscape_ambiguity, pre_select_ambiguous_pairs


def main():
    parser = argparse.ArgumentParser(description="Compute ORD landscape ambiguity scores")
    parser.add_argument("--output", default="data/ambiguity/landscape_ambiguity_report.json")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-score", type=float, default=0.25)
    parser.add_argument("--state", default="enriched", choices=["clean", "enriched"])
    args = parser.parse_args()

    print(f"Loading landscape (state={args.state})...")
    resources = ord_loader.load_landscape(state=args.state)
    print(f"  {len(resources)} total resources")

    print("Computing ambiguity scores (no LLM)...")
    report = compute_landscape_ambiguity(resources, top_k=args.top_k)

    s = report["summary"]
    print(f"\n=== SUMMARY ===")
    print(f"  Total scored resources: {s['total_resources']}")
    print(f"  Easy:      {s['easy']}")
    print(f"  Medium:    {s['medium']}")
    print(f"  Hard:      {s['hard']}")
    print(f"  Very hard: {s['very_hard']}")
    print(f"  Coverage gaps (trivially unique, no distractors): {s['coverage_gaps']}")

    print(f"\n=== BY NAMESPACE ===")
    for ns, ns_data in report["by_namespace"].items():
        print(f"  {ns:25s}  mean={ns_data['mean_ambiguity']:.3f}  "
              f"hard={ns_data['n_hard']:2d}  gaps={ns_data['n_gaps']}")

    print(f"\n=== TOP 10 AMBIGUOUS PAIRS ===")
    for pair in report["top_ambiguous_pairs"][:10]:
        print(f"  {pair['sim']:.3f}  {pair['ordId_A']}")
        print(f"         ←→ {pair['ordId_B']}")
        bd = pair["breakdown"]
        print(f"         usecase={bd.get('useCases', 0) or 0:.2f}  "
              f"et={bd.get('entityTypes', 0) or 0:.2f}  "
              f"caps={bd.get('capabilities', 0) or 0:.2f}  "
              f"tags={bd.get('tags', 0) or 0:.2f}  "
              f"lob={bd.get('lineOfBusiness', 0) or 0:.2f}  "
              f"crossns={bd.get('cross_namespace', 0) or 0:.1f}  "
              f"problems={pair['problems']}")

    print(f"\n=== COVERAGE GAPS (landscape too sparse for test cases) ===")
    gaps = [r for r in report["resources"] if r["coverage_gap"] and r["can_be_ground_truth"]]
    for r in gaps[:10]:
        print(f"  {r['ordId']} ({r['type']})")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))
    print(f"\nFull report written to {output_path}")


if __name__ == "__main__":
    main()
