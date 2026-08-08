"""Reproduce the test-case suite statistics (Paper I, R2/R3 text and Table 5 area).

Covers every reported number about the test-case pipeline, each traced to a log
or output file:

  Process models (design-time enrichment source)
      from data/test_cases/design_time/logs/process_construction_log.json:
      attempts and the accepted / validator-rejected / judge-rejected / gave-up
      / archived breakdown.

  Design-time activity cases
      from data/test_cases/design_time/output/activity_cases.json: total cases
      (30 accepted models x 8 activities = 240).

  Runtime cases per mode
      from data/test_cases/runtime/output/{skill_guided,skill_adjusted,
      dynamic,out_of_scope}.json: accepted case counts.

  Runtime generation effort (Skill-Adjusted + Dynamic solver gate)
      from data/test_cases/runtime/logs/provenance/{sa,dy}-*.json evolution_log:
      total generation iterations and the too-easy / judge-fail breakdown.
      Out-of-Scope: judge-accepted candidates vs. absence-check survivors.

  Certification (5-run re-certification, SA + DY)
      from data/certification/summary.json + results.jsonl: robust counts per
      mode and mean difficulty over SA+DY.

Run:  python3 analysis/test_cases/test_case_stats.py

No API calls. Reads only on-disk logs and outputs.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "src").is_dir())
sys.path.insert(0, str(ROOT))

DT = ROOT / "data" / "test_cases" / "design_time"
RT = ROOT / "data" / "test_cases" / "runtime"
CERT = ROOT / "data" / "certification"
PROV = RT / "logs" / "provenance"


def process_models() -> None:
    log = json.loads((DT / "logs" / "process_construction_log.json").read_text())
    outcomes = Counter(e.get("outcome") for e in log)
    accepted = outcomes.get("ACCEPTED", 0)
    val = outcomes.get("VALIDATOR_FAIL", 0)
    judge = outcomes.get("JUDGE_FAIL", 0)
    gave_up = outcomes.get("GAVE_UP", 0)
    archived = outcomes.get("ARCHIVED", 0)
    attempts = accepted + val + judge + gave_up  # usable attempts (archived excluded)
    print("Process models")
    print(f"  attempts (usable)      : {attempts}")
    print(f"  accepted               : {accepted}")
    print(f"  validator-rejected     : {val}")
    print(f"  judge-rejected         : {judge}")
    print(f"  gave up (retry budget) : {gave_up}")
    if archived:
        print(f"  archived (unused)      : {archived}  (not counted; see _archived/)")


def design_time_cases() -> None:
    cases = json.loads((DT / "output" / "activity_cases.json").read_text())
    n = len(cases) if isinstance(cases, list) else len(cases.get("cases", []))
    print("Design-time cases")
    print(f"  activity cases         : {n}")


def runtime_counts() -> None:
    print("Runtime cases (accepted, per mode)")
    total = 0
    for mode, fn in [("Skill-Guided", "skill_guided"),
                     ("Skill-Adjusted", "skill_adjusted"),
                     ("Dynamic", "dynamic"),
                     ("Out-of-Scope", "out_of_scope")]:
        d = json.loads((RT / "output" / f"{fn}.json").read_text())
        n = len(d) if isinstance(d, list) else len(d.get("cases", []))
        total += n
        print(f"  {mode:15}: {n}")
    print(f"  {'total':15}: {total}")


def _evolution_outcomes(prefixes: list[str]) -> tuple[int, Counter]:
    iters = 0
    oc: Counter = Counter()
    for pref in prefixes:
        for f in PROV.glob(f"{pref}-*.json"):
            for e in json.loads(f.read_text()).get("evolution_log", []):
                iters += 1
                oc[str(e.get("outcome"))] += 1
    return iters, oc


def runtime_generation_effort() -> None:
    iters, oc = _evolution_outcomes(["sa", "dy"])
    known = {"ACCEPTED", "TOO_EASY", "JUDGE_FAIL"}
    other = sum(v for k, v in oc.items() if k not in known)
    print("Runtime generation effort (Skill-Adjusted + Dynamic solver gate)")
    print(f"  generation iterations  : {iters}")
    print(f"  rejected too-easy      : {oc.get('TOO_EASY', 0)}")
    print(f"  rejected by Judge      : {oc.get('JUDGE_FAIL', 0)}")
    if other:
        print(f"  other/incomplete       : {other}  (mid-regeneration steps with no final label)")

    # Out-of-Scope: judge-accepted candidates vs. absence-check survivors
    _, oos = _evolution_outcomes(["oos"])
    oos_accepted = oos.get("ACCEPTED", 0)
    oos_final = len(json.loads((RT / "output" / "out_of_scope.json").read_text()))
    print("Out-of-Scope absence check")
    print(f"  judge-accepted candidates : {oos_accepted}")
    print(f"  judge-rejected            : {oos.get('JUDGE_FAIL', 0)}")
    print(f"  survived absence check    : {oos_final}")
    print(f"  removed by absence check  : {oos_accepted - oos_final}")


def skill_artefacts() -> None:
    """Skill artefacts (one per accepted process model). The construction log is
    partial (covers the first pass only); the authoritative count is the .md
    files on disk."""
    log_path = DT / "logs" / "skill_construction_log.json"
    skills = list((DT / "output" / "skills").glob("*.md"))
    logged = json.loads(log_path.read_text()) if log_path.exists() else []
    oc = Counter(e.get("outcome") for e in logged) if isinstance(logged, list) else {}
    print("Skill artefacts")
    print(f"  skill files on disk    : {len(skills)}")
    print(f"  construction-log rows  : {len(logged)}  outcomes={dict(oc)}  (partial log)")


def certification() -> None:
    summary = json.loads((CERT / "summary.json").read_text())
    bm = summary["by_mode"]
    sa = bm["skill_adjusted"]["robust"]
    dy = bm["dynamic"]["robust"]
    runs = summary.get("n_runs_per_case")
    results = [json.loads(l) for l in (CERT / "results.jsonl").read_text().splitlines() if l.strip()]
    sadv = [r for r in results if r["mode"] in ("skill_adjusted", "dynamic")]
    avg = sum(r["difficulty"] for r in sadv) / len(sadv) if sadv else 0.0
    print(f"Certification ({runs}-run, strict: solved in 0 of {runs})")
    print(f"  Skill-Adjusted robust  : {sa}/20")
    print(f"  Dynamic robust         : {dy}/40")
    print(f"  SA+DY robust           : {sa + dy}/60 ({100 * (sa + dy) / 60:.1f}%)")
    print(f"  SA+DY mean difficulty  : {avg:.4f}")


def main() -> None:
    for section in (process_models, skill_artefacts, design_time_cases,
                    runtime_counts, runtime_generation_effort, certification):
        section()
        print()


if __name__ == "__main__":
    main()
