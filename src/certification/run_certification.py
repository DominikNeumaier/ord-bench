"""Post-hoc multi-run certification for runtime in-scope cases.

Each case that passed the original Method-S gate is re-run 4 more times.
Combined with the original gate run (assumed = fail), every case has 5 samples.

  difficulty = failed_runs / 5

A case is "robustly certified" when difficulty >= 0.80 (S fails in >=4/5 runs).

Usage:
    python data/certification/run_certification.py
    python data/certification/run_certification.py --extra-runs 4
    python data/certification/run_certification.py --modes dynamic
    python data/certification/run_certification.py --no-resume   # re-run all
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

# ── project root on sys.path ─────────────────────────────────────────────────
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src import loader as ord_loader, config
from src.methods import method_s

# ── paths ────────────────────────────────────────────────────────────────────
CERT_DIR = Path(__file__).parent
RUNS_DIR  = CERT_DIR / "runs"
RESULTS_PATH = CERT_DIR / "results.jsonl"
SUMMARY_PATH = CERT_DIR / "summary.json"
REPORT_PATH  = CERT_DIR / "report.md"

ROBUST_THRESHOLD = 0.80   # difficulty >= this → robustly certified
BORDERLINE_THRESHOLD = 0.60  # difficulty in [0.60, 0.80) → borderline

PROV_DIR = ROOT / "data" / "test_cases" / "runtime" / "logs" / "provenance"
DY_CASES = ROOT / "data" / "test_cases" / "runtime" / "output" / "dynamic.json"


def _load_provenance_ords() -> dict[str, list[str]]:
    """Load expected ORD IDs from provenance logs (authoritative source)."""
    result: dict[str, list[str]] = {}
    if PROV_DIR.exists():
        for f in PROV_DIR.glob("*.json"):
            try:
                p = json.loads(f.read_text())
                cid = p.get("case_id")
                if not cid:
                    continue
                # SA/SG: gap_resources field
                ords = p.get("gap_resources", [])
                # DY: selected_resources field
                if not ords:
                    ords = p.get("selected_resources", [])
                if ords:
                    result[cid] = ords
            except Exception:
                pass
    # Fallback: dynamic.json has expected_ordIds
    try:
        dy_cases = json.loads(DY_CASES.read_text())
        for c in dy_cases:
            cid = c.get("case_id")
            if cid and cid not in result:
                ords = c.get("expected_ordIds", [])
                if ords:
                    result[cid] = ords
    except Exception:
        pass
    return result


_PROV_ORDS: dict[str, list[str]] = {}  # loaded lazily


def load_in_scope_cases() -> list[dict]:
    """Load all in-scope cases from the benchmark records (one per case_id × mode)."""
    cases: dict[str, dict] = {}
    for mode in ["skill_guided", "skill_adjusted", "dynamic"]:
        rec_path = ROOT / "results" / "runtime" / mode / "records.jsonl"
        if not rec_path.exists():
            continue
        with rec_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Only take one record per case (S0 preferred; any otherwise)
                cid = r["case_id"]
                if cid in cases:
                    # prefer S0 for prompt/metadata
                    if r.get("condition") == "S0":
                        cases[cid] = r
                else:
                    cases[cid] = r

    # Filter: only in-scope (mode_expected != out_of_scope)
    return [
        r for r in cases.values()
        if r.get("mode_expected") in ("skill_guided", "skill_adjusted", "dynamic")
    ]


def load_resources() -> list[dict]:
    return ord_loader.load_landscape(state="clean")


def run_single(prompt: str, resources: list[dict], expected_ordIds: list[str]) -> dict:
    """Run Method S once and return outcome dict."""
    t0 = time.time()
    result = method_s.retrieve(prompt, resources, top_k=1)
    wall = round(time.time() - t0, 3)

    candidates = result.get("candidates", [])
    picked_id  = candidates[0]["ordId"] if candidates else None
    solved     = picked_id in expected_ordIds if expected_ordIds else False

    return {
        "picked_ordId": picked_id,
        "solved": solved,
        "tokens": result["trace"]["tokens"],
        "latency_s": result["trace"]["latency_s"],
        "wall_s": wall,
    }


def get_expected_ords(case_record: dict) -> list[str]:
    """Get expected ORD IDs from provenance logs (authoritative gate source)."""
    global _PROV_ORDS
    if not _PROV_ORDS:
        _PROV_ORDS = _load_provenance_ords()
    cid = case_record["case_id"]
    return _PROV_ORDS.get(cid, [])


def load_existing_runs(case_id: str) -> list[dict]:
    """Load already-completed extra runs for a case (for resuming)."""
    case_dir = RUNS_DIR / case_id
    if not case_dir.exists():
        return []
    runs = []
    for p in sorted(case_dir.glob("run_*.json")):
        try:
            runs.append(json.loads(p.read_text()))
        except Exception:
            pass
    return runs


def save_run(case_id: str, run_idx: int, outcome: dict) -> None:
    case_dir = RUNS_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    path = case_dir / f"run_{run_idx:02d}.json"
    path.write_text(json.dumps(outcome, indent=2))


def certify_all(cases: list[dict], resources: list[dict],
                extra_runs: int, resume: bool) -> list[dict]:
    """Run certification for all cases. Returns list of result dicts."""
    results = []

    for i, case in enumerate(cases):
        cid      = case["case_id"]
        mode     = case.get("mode_expected", "?")
        prompt   = case.get("user_prompt", "")
        exp_ords = get_expected_ords(case)

        # Original gate outcome: gate passed = S failed = solved=False
        # We treat the original gate as run_00 (S failed → solved=False)
        gate_outcome = {"run": 0, "source": "original_gate", "solved": False,
                        "picked_ordId": None, "tokens": 0, "latency_s": 0.0}

        # Load or run extra runs
        existing = load_existing_runs(cid) if resume else []
        extra_outcomes = []
        for run_idx in range(1, extra_runs + 1):
            # Check if already done
            done = next((r for r in existing if r.get("run") == run_idx), None)
            if done:
                print(f"  [{i+1}/{len(cases)}] {cid} run {run_idx}/{extra_runs} (cached)")
                extra_outcomes.append(done)
            else:
                print(f"  [{i+1}/{len(cases)}] {cid} run {run_idx}/{extra_runs} ...", end=" ", flush=True)
                outcome = run_single(prompt, resources, exp_ords)
                outcome["run"] = run_idx
                save_run(cid, run_idx, outcome)
                extra_outcomes.append(outcome)
                status = "SOLVED" if outcome["solved"] else "failed"
                print(status)

        all_runs = [gate_outcome] + extra_outcomes
        total_runs = len(all_runs)
        failed_runs = sum(1 for r in all_runs if not r["solved"])
        difficulty  = round(failed_runs / total_runs, 4)

        result = {
            "case_id":       cid,
            "mode":          mode,
            "user_prompt":   prompt,
            "expected_ords": exp_ords,
            "total_runs":    total_runs,
            "failed_runs":   failed_runs,
            "solved_runs":   total_runs - failed_runs,
            "difficulty":    difficulty,
            "robust":        difficulty >= ROBUST_THRESHOLD,
            "borderline":    BORDERLINE_THRESHOLD <= difficulty < ROBUST_THRESHOLD,
            "too_easy":      difficulty < BORDERLINE_THRESHOLD,
            "runs":          all_runs,
        }
        results.append(result)

    return results


def write_results(results: list[dict]) -> None:
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    # results.jsonl — one line per case
    with RESULTS_PATH.open("w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    # summary.json
    total      = len(results)
    robust     = sum(1 for r in results if r["robust"])
    borderline = sum(1 for r in results if r["borderline"])
    too_easy   = sum(1 for r in results if r["too_easy"])
    avg_diff   = round(sum(r["difficulty"] for r in results) / total, 4) if total else 0

    by_mode: dict[str, dict] = {}
    for r in results:
        m = r["mode"]
        if m not in by_mode:
            by_mode[m] = {"total": 0, "robust": 0, "borderline": 0, "too_easy": 0}
        by_mode[m]["total"]      += 1
        by_mode[m]["robust"]     += int(r["robust"])
        by_mode[m]["borderline"] += int(r["borderline"])
        by_mode[m]["too_easy"]   += int(r["too_easy"])

    summary = {
        "total_cases":        total,
        "robust_certified":   robust,
        "borderline":         borderline,
        "too_easy":           too_easy,
        "pct_robust":         round(robust / total * 100, 1) if total else 0,
        "avg_difficulty":     avg_diff,
        "threshold_robust":   ROBUST_THRESHOLD,
        "threshold_borderline": BORDERLINE_THRESHOLD,
        "extra_runs":         max((r["total_runs"] for r in results), default=0) - 1,
        "by_mode":            by_mode,
        "borderline_cases":   [r["case_id"] for r in results if r["borderline"]],
        "too_easy_cases":     [r["case_id"] for r in results if r["too_easy"]],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))

    # report.md
    lines = [
        "# Baseline-Solver Certification Report",
        "",
        "## Method",
        "",
        f"Each of the {total} in-scope cases was run through Method S (no-retrieval "
        f"LLM baseline) **{summary['extra_runs'] + 1} times** in total: the original "
        "gate run (outcome = fail, by definition of case acceptance) plus "
        f"{summary['extra_runs']} independent re-runs.",
        "",
        "A case is **robustly certified** when S fails in "
        f"≥ {int(ROBUST_THRESHOLD * (summary['extra_runs']+1))}/{summary['extra_runs']+1} runs "
        f"(difficulty ≥ {ROBUST_THRESHOLD}).",
        "",
        "## Results",
        "",
        f"| Category | Count | % |",
        f"|---|---|---|",
        f"| Robustly certified (difficulty ≥ {ROBUST_THRESHOLD}) | {robust} | {summary['pct_robust']}% |",
        f"| Borderline (difficulty {BORDERLINE_THRESHOLD}–{ROBUST_THRESHOLD}) | {borderline} | {round(borderline/total*100,1)}% |",
        f"| Too easy (difficulty < {BORDERLINE_THRESHOLD}) | {too_easy} | {round(too_easy/total*100,1)}% |",
        f"| **Total** | **{total}** | 100% |",
        "",
        f"Average difficulty across all cases: **{avg_diff}**",
        "",
        "## By Mode",
        "",
        "| Mode | Total | Robust | Borderline | Too Easy |",
        "|---|---|---|---|---|",
    ]
    for mode, stats in by_mode.items():
        lines.append(
            f"| {mode} | {stats['total']} | {stats['robust']} "
            f"| {stats['borderline']} | {stats['too_easy']} |"
        )
    lines += [
        "",
        "## Borderline Cases",
        "",
    ]
    if summary["borderline_cases"]:
        for cid in summary["borderline_cases"]:
            r = next(x for x in results if x["case_id"] == cid)
            lines.append(f"- **{cid}** ({r['mode']}) difficulty={r['difficulty']} "
                         f"— S solved in {r['solved_runs']}/{r['total_runs']} runs")
    else:
        lines.append("None.")

    lines += [
        "",
        "## Too-Easy Cases (should be reviewed)",
        "",
    ]
    if summary["too_easy_cases"]:
        for cid in summary["too_easy_cases"]:
            r = next(x for x in results if x["case_id"] == cid)
            lines.append(f"- **{cid}** ({r['mode']}) difficulty={r['difficulty']} "
                         f"— S solved in {r['solved_runs']}/{r['total_runs']} runs")
            lines.append(f"  Prompt: _{r['user_prompt'][:120]}_")
    else:
        lines.append("None.")

    REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nWrote: {RESULTS_PATH.relative_to(ROOT)}")
    print(f"Wrote: {SUMMARY_PATH.relative_to(ROOT)}")
    print(f"Wrote: {REPORT_PATH.relative_to(ROOT)}")


def print_summary(results: list[dict]) -> None:
    total      = len(results)
    robust     = sum(1 for r in results if r["robust"])
    borderline = sum(1 for r in results if r["borderline"])
    too_easy   = sum(1 for r in results if r["too_easy"])
    print(f"\n{'='*55}")
    print(f"  Certification complete — {total} cases, "
          f"{max(r['total_runs'] for r in results)} runs each")
    print(f"{'='*55}")
    print(f"  Robustly certified (diff >= {ROBUST_THRESHOLD}): "
          f"{robust}/{total} ({robust/total*100:.1f}%)")
    print(f"  Borderline                 : {borderline}/{total}")
    print(f"  Too easy                   : {too_easy}/{total}")
    print(f"  Avg difficulty             : "
          f"{sum(r['difficulty'] for r in results)/total:.3f}")
    if too_easy:
        print(f"\n  TOO-EASY CASES (review before final submission):")
        for r in results:
            if r["too_easy"]:
                print(f"    {r['case_id']} [{r['mode']}] diff={r['difficulty']} "
                      f"S-solved {r['solved_runs']}/{r['total_runs']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Post-hoc multi-run S certification")
    ap.add_argument("--extra-runs", type=int, default=4,
                    help="extra runs per case beyond the original gate (default=4)")
    ap.add_argument("--modes", nargs="+",
                    choices=["skill_guided","skill_adjusted","dynamic"],
                    default=None, help="restrict to these modes")
    ap.add_argument("--no-resume", action="store_true",
                    help="ignore cached runs and re-run everything")
    args = ap.parse_args()

    print("Loading in-scope cases...")
    cases = load_in_scope_cases()
    if args.modes:
        cases = [c for c in cases if c.get("mode_expected") in args.modes]
    print(f"  {len(cases)} in-scope cases found")

    print("Loading resources (clean ORD)...")
    resources = load_resources()
    print(f"  {len(resources)} resources")

    print(f"\nRunning {args.extra_runs} extra certification runs per case "
          f"(resume={'no' if args.no_resume else 'yes'})...")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    results = certify_all(cases, resources,
                          extra_runs=args.extra_runs,
                          resume=not args.no_resume)

    write_results(results)
    print_summary(results)


if __name__ == "__main__":
    main()
