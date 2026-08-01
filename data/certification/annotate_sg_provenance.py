"""Append a `post_gate_rewrite` block to all 30 SG provenance logs.

The block documents that the original SG prompts (which went through Method-S
gate during initial generation) were shortened post-gate in commit 6429a4cac
to clean up routing-eval noise, and that the final prompts were re-validated
by the v2 5-run certification (benchmark/certification/v2/).

This script is idempotent — it only adds the block if it does not already exist.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROV_DIR = ROOT / "benchmark" / "test_cases" / "runtime" / "logs" / "provenance"
SG_CASE_FILE = ROOT / "benchmark" / "test_cases" / "runtime" / "output" / "skill_guided.json"
V2_RESULTS = ROOT / "benchmark" / "certification" / "v2" / "results.jsonl"

REWRITE_COMMIT = "6429a4cac"
REWRITE_REASON = (
    "Original long enumerative prompts were classified as 'skill_adjusted' by "
    "the planner (Routing-Acc 0.700 on the eval_sg_routing pass), because each "
    "enumerated sub-activity looked like a separate step. The prompts were "
    "shortened to retain the same business intent (same skill, same expected "
    "ordIds) while making the single-skill routing intent unambiguous."
)


def main() -> None:
    # Load current (= post-rewrite) prompts from the test case file
    sg_cases = json.loads(SG_CASE_FILE.read_text())
    final_prompts = {c["case_id"]: c["user_prompt"] for c in sg_cases}

    # Load v2 recertification results
    v2_by_case: dict[str, dict] = {}
    if V2_RESULTS.exists():
        for line in V2_RESULTS.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            v2_by_case[r["case_id"]] = r

    updated = 0
    skipped = 0
    for cid, final_prompt in final_prompts.items():
        prov_path = PROV_DIR / f"{cid}.json"
        if not prov_path.exists():
            print(f"  missing provenance: {cid}")
            continue

        prov = json.loads(prov_path.read_text())
        # idempotent guard
        if "post_gate_rewrite" in prov:
            skipped += 1
            continue

        orig_prompt = prov.get("accepted_case", {}).get("user_prompt", "")
        # sanity: skill_id and expected ordIds preserved?
        case_in_file = next((c for c in sg_cases if c["case_id"] == cid), None)
        preserved = []
        changed = ["user_prompt"]
        if case_in_file:
            case_ords = []
            for s in case_in_file.get("expected_steps", []):
                case_ords.extend(s.get("expected_ordIds", []))
            prov_ords = []
            for s in prov.get("accepted_case", {}).get("expected_steps", []):
                prov_ords.extend(s.get("expected_ordIds", []))
            if set(case_ords) == set(prov_ords):
                preserved.append("expected_ordIds")
            if case_in_file.get("skill_id") == prov.get("skill_id"):
                preserved.append("skill_id")

        v2 = v2_by_case.get(cid)
        recert = None
        if v2:
            recert = {
                "n_runs":      v2["n_runs"],
                "solved_runs": v2["solved_runs"],
                "failed_runs": v2["failed_runs"],
                "difficulty":  v2["difficulty"],
                "robust":      v2["robust"],
                "borderline":  v2["borderline"],
                "too_easy":    v2["too_easy"],
                "method":      "post-hoc 5-run Method-S re-evaluation on the "
                               "final (rewritten) prompt with per-run nonce "
                               "cache bypass; see benchmark/certification/v2/",
            }

        prov["post_gate_rewrite"] = {
            "rewritten_after_gate":  True,
            "reason":                REWRITE_REASON,
            "commit":                REWRITE_COMMIT,
            "preserved":             preserved,
            "changed":               changed,
            "original_user_prompt":  orig_prompt,
            "final_user_prompt":     final_prompt,
            "original_chars":        len(orig_prompt),
            "final_chars":           len(final_prompt),
            "solver_recertification": recert,
        }
        prov_path.write_text(json.dumps(prov, indent=2))
        updated += 1
        print(f"  {cid} updated  preserved={preserved}  recert.robust={recert and recert['robust']}")

    print(f"\nUpdated {updated} provenance logs (skipped {skipped} already-annotated).")


if __name__ == "__main__":
    main()
