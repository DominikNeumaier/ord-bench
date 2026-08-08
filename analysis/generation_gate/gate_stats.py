"""Reproduce the landscape generation-gate statistics (Paper I, R1 text).

Reads the reduced generation log (final run only) and reports, for the LLM
Judge stage:
  - total candidates rejected by the Judge (rejected_judge)
  - the most common rejection reasons, from the judge_verdict flags
    (a single candidate can fail several checks, so these overlap):
      domain incoherence     -> c2_coherent == False
      unjustified entityTypes -> c4_et_justified == False
      duplication            -> c3_not_duplicate == False
  - candidates rejected by the deterministic pre-check before any LLM call
    (rejected_c1) and wrong-tier placements (wrong_tier)

Run:  python3 analysis/generation_gate/gate_stats.py

No API calls. Reads only the generation log.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "src").is_dir())
sys.path.insert(0, str(ROOT))

LOG_PATH = ROOT / "data" / "landscape" / "logs" / "enrichment_log.json"


def main() -> None:
    log = json.loads(LOG_PATH.read_text())
    it = [e for e in log if e.get("phase") == "iterative"]

    rejected_judge = [e for e in it if e.get("outcome") == "rejected_judge"]
    rejected_pre = [e for e in it if e.get("outcome") == "rejected_c1"]
    wrong_tier = [e for e in it if e.get("outcome") == "wrong_tier"]
    accepted = [e for e in it if e.get("outcome") == "accepted"]
    created = [e for e in it if e.get("action") == "create"]

    incoherence = entitytypes = duplication = 0
    for e in rejected_judge:
        v = e.get("judge_verdict", {})
        if v.get("c2_coherent") is False:
            incoherence += 1
        if v.get("c4_et_justified") is False:
            entitytypes += 1
        if v.get("c3_not_duplicate") is False:
            duplication += 1

    reached_judge = len(accepted) + len(rejected_judge)
    rate = 100 * len(accepted) / reached_judge if reached_judge else 0.0

    print("Landscape generation gate (final run)")
    print("-" * 44)
    print(f"create attempts (validator-passed): {len(created)}")
    print(f"reached the Judge (acc + rej)      : {reached_judge}")
    print(f"  accepted                         : {len(accepted)}")
    print(f"  rejected by Judge                : {len(rejected_judge)}")
    print(f"  acceptance rate                  : {rate:.0f}%")
    print(f"    domain incoherence (c2)        : {incoherence}")
    print(f"    unjustified entityTypes (c4)   : {entitytypes}")
    print(f"    duplication (c3)               : {duplication}")
    print(f"  wrong tier (did not reach Judge) : {len(wrong_tier)}")
    print(f"rejected by pre-check (c1)         : {len(rejected_pre)}")


if __name__ == "__main__":
    main()
