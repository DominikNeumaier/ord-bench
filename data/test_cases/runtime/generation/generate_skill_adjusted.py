"""Generate Skill-Adjusted run-time cases (20: Implicit Multi-Step).

Base: 1 Skill-Guided skill + 1-3 gap resources (sim ≥ 0.25, NOT in skill, GT-eligible).
Generator extends the skill scenario implicitly.
Mutator loop until Solver@273-clean fails on gap steps.

Output: benchmark/test_cases/runtime/output/skill_adjusted.json
        benchmark/test_cases/runtime/logs/provenance/sa-*.json
"""
from __future__ import annotations

import json
import re
import sys
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from benchmark.test_cases.runtime.generation._common import (
    load_resources, load_ambiguity, load_skills, get_resource_by_id,
    solver_check, save_provenance, save_output, now_iso, MAX_ITERATIONS,
)
from src.core import llm

TARGET = 20
MAX_ATTEMPTS_PER_CASE = MAX_ITERATIONS
RANDOM_SEED = 43
GAP_MIN_SIM = 0.25


def find_gap_resources(skill: dict, ambiguity: dict[str, dict],
                       resources: list[dict], rng: random.Random, n: int = 2) -> list[dict]:
    """Find GT-eligible resources not in skill with sim ≥ GAP_MIN_SIM to any skill resource."""
    skill_ids = set(skill["gt_ord_ids"])
    candidates = []
    for r in resources:
        oid = r["ordId"]
        if oid in skill_ids:
            continue
        amb = ambiguity.get(oid, {})
        if not amb.get("ground_truth_eligible"):
            continue
        # check if any neighbor of this resource is in the skill
        neighbors = {nb["ordId"]: nb["sim"] for nb in amb.get("all_neighbors", [])}
        max_sim = max((neighbors.get(sid, 0) for sid in skill_ids), default=0)
        if max_sim >= GAP_MIN_SIM:
            candidates.append((max_sim, r))
    candidates.sort(key=lambda x: -x[0])
    selected = [r for _, r in candidates[:n * 3]]
    return rng.sample(selected, min(n, len(selected))) if len(selected) >= n else selected


def validate(prompt: str, gap_ids: list[str], skill_ids: set[str],
             resources: list[dict]) -> tuple[bool, str]:
    all_ids = {r["ordId"] for r in resources}
    missing = [o for o in gap_ids if o not in all_ids]
    if missing:
        return False, f"V1: unknown gap ordIds: {missing[:2]}"
    in_skill = [o for o in gap_ids if o in skill_ids]
    if in_skill:
        return False, f"V2: gap ordIds in skill: {in_skill}"
    if len(prompt.strip()) < 20:
        return False, "V3: prompt too short"
    return True, ""


def judge(prompt: str, skill: dict, gap_ids: list[str]) -> tuple[bool, dict, str, int]:
    sys_p = (
        "You are a pragmatic quality judge for a synthetic enterprise benchmark. "
        "Answer ONLY with valid JSON."
    )
    user_p = f"""Review this Skill-Adjusted case.

user_prompt: {prompt}
base_skill: {skill['skill_id']} — {skill['description'][:200]}
gap_step_ordIds: {gap_ids}

Return JSON:
{{
  "C1": true/false,  // base skill covers the core request (not the gaps)
  "C2": true/false,  // gap dependencies are implied, not stated explicitly
  "C3": true/false,  // overall request sounds coherent as one enterprise scenario
  "accepted": true/false,
  "reason": "one sentence if rejected"
}}"""
    text, meta = llm.chat(user_p, system=sys_p)
    try:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        data = json.loads(m.group()) if m else {}
        results = {f"C{i}": data.get(f"C{i}") for i in range(1, 4)}
        return bool(data.get("accepted", False)), results, text, meta["tokens"]
    except Exception:
        return False, {f"C{i}": None for i in range(1, 4)}, text, meta["tokens"]


def build_prompt(skill: dict, gap_resources: list[dict], variant: int = 0) -> str:
    gap_block = "\n".join(
        f"  - {r['title']}: {r.get('shortDescription', '')[:80]}"
        for r in gap_resources
    )
    mutation_hint = ""
    if variant == 1:
        mutation_hint = "Use synonym vocabulary — avoid the exact words from the skill description."
    elif variant >= 2:
        mutation_hint = "Describe the business NEED, not the resource type or system. Use implicit references."

    return f"""Create a user request that covers a {skill['process_type'].upper()} skill scenario AND additional implicit steps.

Skill scenario: {skill['description'][:200]}

Additional steps that must be IMPLICITLY required (do NOT name these directly):
{gap_block}

Rules:
- The main request should match the skill scenario
- The additional steps should be implied by context ("and we also need to...", "including...", "as well as...")
- Do NOT name any resource, API, system, or ordId
- 3-5 sentences total
{mutation_hint}

Output ONLY the user prompt text."""


def run():
    resources = load_resources("clean")
    ambiguity = load_ambiguity()
    skills = load_skills()
    rng = random.Random(RANDOM_SEED)

    accepted_cases = []
    rng.shuffle(skills)

    print(f"Generating {TARGET} Skill-Adjusted cases...")

    for skill in skills:
        if len(accepted_cases) >= TARGET:
            break

        gap_resources = find_gap_resources(skill, ambiguity, resources, rng, n=2)
        if not gap_resources:
            continue

        gap_ids = [r["ordId"] for r in gap_resources]
        skill_ids = set(skill["gt_ord_ids"])
        print(f"\n[{skill['skill_id']}] gaps: {gap_ids}...")

        evolution_log = []

        for attempt in range(1, MAX_ATTEMPTS_PER_CASE + 1):
            variant = attempt - 1
            prompt_input = build_prompt(skill, gap_resources, variant)
            user_prompt, gen_meta = llm.chat(prompt_input)
            user_prompt = user_prompt.strip().strip('"')

            v_ok, v_fail = validate(user_prompt, gap_ids, skill_ids, resources)
            if not v_ok:
                print(f"  attempt {attempt}: VALIDATOR FAIL — {v_fail}")
                evolution_log.append({"iteration": attempt, "outcome": "VALIDATOR_FAIL",
                                      "validator_failure": v_fail})
                continue

            solver_correct, solver_pred = solver_check(user_prompt, resources, gap_ids)
            if solver_correct:
                print(f"  attempt {attempt}: TOO_EASY on gap steps")
                evolution_log.append({"iteration": attempt, "outcome": "TOO_EASY",
                                      "solver_output": {"predicted": solver_pred}})
                continue

            j_ok, j_results, j_response, j_tokens = judge(user_prompt, skill, gap_ids)
            entry = {
                "iteration": attempt,
                "generator_output": {"user_prompt": user_prompt, "variant": variant},
                "generator_tokens": gen_meta["tokens"],
                "solver_output": {"predicted": solver_pred, "correct": False},
                "judge_results": j_results,
                "judge_response": j_response[:300],
                "judge_tokens": j_tokens,
                "outcome": "ACCEPTED" if j_ok else "JUDGE_FAIL",
            }
            evolution_log.append(entry)

            if not j_ok:
                print(f"  attempt {attempt}: JUDGE FAIL")
                continue

            case_id = f"sa-{len(accepted_cases)+1:02d}"
            case = {
                "case_id": case_id,
                "mode": "skill_adjusted",
                "query_class": "implicit_multi_step",
                "user_prompt": user_prompt,
                "expected_skill_id": skill["skill_id"],
                "expected_gap_ordIds": gap_ids,
            }
            save_provenance(case_id, {
                "case_id": case_id, "mode": "skill_adjusted",
                "skill_id": skill["skill_id"], "gap_resources": gap_ids,
                "timestamp": now_iso(), "evolution_log": evolution_log,
                "accepted_case": case,
            })
            accepted_cases.append(case)
            print(f"  attempt {attempt}: ACCEPTED → {case_id} ({len(accepted_cases)}/{TARGET})")
            break
        else:
            print(f"  GAVE UP after {MAX_ATTEMPTS_PER_CASE} attempts")

    save_output("skill_adjusted.json", accepted_cases)
    print(f"\nDone. {len(accepted_cases)}/{TARGET} Skill-Adjusted cases accepted.")


if __name__ == "__main__":
    run()
