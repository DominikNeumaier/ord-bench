"""Generate Skill-Guided run-time cases (30: Explicit + Conditional Multi-Step).

For each accepted process model:
  Generator → user_prompt (no resource names, no skill references)
  Solver@273-clean → must fail on skill_id + first GT step
  Validator (script) → V1-V3
  Judge (LLM) → C1-C5

Output: benchmark/test_cases/runtime/output/skill_guided.json
        benchmark/test_cases/runtime/logs/provenance/sg-*.json
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
    load_resources, load_skills, get_resource_by_id,
    solver_check, save_provenance, save_output, now_iso, MAX_ITERATIONS,
)
from src.core import llm

TARGET = 30
MAX_ATTEMPTS_PER_CASE = MAX_ITERATIONS
RANDOM_SEED = 42


def validate(prompt: str, expected_ord_ids: list[str], resources: list[dict]) -> tuple[bool, str]:
    """V1-V3 deterministic checks."""
    all_ids = {r["ordId"] for r in resources}
    # V1: ordIds exist
    missing = [o for o in expected_ord_ids if o not in all_ids]
    if missing:
        return False, f"V1: unknown ordIds: {missing[:2]}"
    # V2: prompt not empty
    if len(prompt.strip()) < 20:
        return False, "V2: prompt too short"
    # V3: no ordId or resource title literally in prompt
    for oid in expected_ord_ids:
        local_id = oid.split(":")[2] if ":" in oid else oid
        if local_id.lower() in prompt.lower():
            return False, f"V3: ordId fragment '{local_id}' found in prompt"
    return True, ""


def judge(prompt: str, process_type: str, expected_ord_ids: list[str]) -> tuple[bool, dict, str, int]:
    sys_p = (
        "You are a quality judge for a synthetic enterprise benchmark. "
        "Be pragmatic — accept prompts that are plausible and well-structured. "
        "Answer ONLY with valid JSON."
    )
    user_p = f"""Review this {process_type.upper()} skill-guided case.

user_prompt: {prompt}
process_type: {process_type}
expected GT ordIds: {expected_ord_ids}

Return JSON:
{{
  "C1": true/false,  // prompt sounds like real enterprise request
  "C2": true/false,  // prompt coherent with a {process_type} process scenario
  "C3": true/false,  // no resource names or skill names in prompt
  "C4": true/false,  // skill could plausibly cover request end-to-end
  "C5": true/false,  // prompt has natural language complexity (not trivially obvious)
  "accepted": true/false,
  "reason": "one sentence if rejected"
}}"""
    text, meta = llm.chat(user_p, system=sys_p)
    try:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        data = json.loads(m.group()) if m else {}
        results = {f"C{i}": data.get(f"C{i}") for i in range(1, 6)}
        return bool(data.get("accepted", False)), results, text, meta["tokens"]
    except Exception:
        return False, {f"C{i}": None for i in range(1, 6)}, text, meta["tokens"]


def build_prompt(skill: dict, process_type: str, gt_resources: list[dict]) -> str:
    gt_block = "\n".join(
        f"  - Step resource: {r['title']} ({r.get('shortDescription','')[:80]})"
        for r in gt_resources
    )
    return f"""Create a natural-language enterprise user request for a {process_type.upper()} skill.

The skill covers these activities (DO NOT mention these directly):
{gt_block}

Rules:
- Sound like a real enterprise user asking for help (e.g. "We need to...", "Help us...", "Our team needs to...")
- Do NOT name any resource, system, ordId, or skill name
- Make it specific enough to suggest a multi-step process
- 2-4 sentences

Output ONLY the user prompt text, nothing else."""


def run():
    resources = load_resources("clean")
    skills = load_skills()
    rng = random.Random(RANDOM_SEED)

    accepted_cases = []
    rng.shuffle(skills)

    print(f"Generating {TARGET} Skill-Guided cases from {len(skills)} skills...")

    # Allow re-use of skills if first pass doesn't reach TARGET
    skills_pool = skills * 3  # up to 3 passes through skill list

    for skill in skills_pool:
        if len(accepted_cases) >= TARGET:
            break

        skill_id = skill["skill_id"]
        # skip if already produced 2 cases from this skill
        if sum(1 for c in accepted_cases if c["skill_id"] == skill_id) >= 2:
            continue

        gt_ids = skill["gt_ord_ids"]
        if not gt_ids:
            continue

        gt_resources = [r for oid in gt_ids if (r := get_resource_by_id(resources, oid))]
        if not gt_resources:
            continue

        process_type = skill["process_type"]
        print(f"\n[{skill_id}] {process_type.upper()} | GT: {gt_ids[:2]}...")

        evolution_log = []

        for attempt in range(1, MAX_ATTEMPTS_PER_CASE + 1):
            prompt_input = build_prompt(skill, process_type, gt_resources)
            user_prompt, gen_meta = llm.chat(prompt_input)
            user_prompt = user_prompt.strip().strip('"')

            v_ok, v_fail = validate(user_prompt, gt_ids, resources)
            if not v_ok:
                print(f"  attempt {attempt}: VALIDATOR FAIL — {v_fail}")
                evolution_log.append({"iteration": attempt, "outcome": "VALIDATOR_FAIL",
                                      "validator_failure": v_fail, "generator_output": {"user_prompt": user_prompt}})
                continue

            solver_correct, solver_pred = solver_check(user_prompt, resources, gt_ids[:1])
            if solver_correct:
                print(f"  attempt {attempt}: TOO_EASY (solver got it)")
                evolution_log.append({"iteration": attempt, "outcome": "TOO_EASY",
                                      "solver_output": {"predicted": solver_pred, "correct": True},
                                      "generator_output": {"user_prompt": user_prompt}})
                continue

            j_ok, j_results, j_response, j_tokens = judge(user_prompt, process_type, gt_ids)
            entry = {
                "iteration": attempt,
                "generator_output": {"user_prompt": user_prompt},
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

            case_id = f"sg-{len(accepted_cases)+1:02d}"
            case = {
                "case_id": case_id,
                "mode": "skill_guided",
                "query_class": "conditional_multi_step" if process_type == "cmmn" else "explicit_multi_step",
                "skill_id": skill_id,
                "process_type": process_type,
                "user_prompt": user_prompt,
                "expected_skill_id": skill_id,
                "expected_steps": [{"step_name": f"step_{i+1}", "expected_ordIds": [oid]}
                                   for i, oid in enumerate(gt_ids)],
            }
            save_provenance(case_id, {
                "case_id": case_id, "mode": "skill_guided",
                "skill_id": skill_id, "selected_resources": gt_ids,
                "timestamp": now_iso(), "evolution_log": evolution_log,
                "accepted_case": case,
            })
            accepted_cases.append(case)
            print(f"  attempt {attempt}: ACCEPTED → {case_id} ({len(accepted_cases)}/{TARGET})")
            break
        else:
            print(f"  GAVE UP after {MAX_ATTEMPTS_PER_CASE} attempts")

    save_output("skill_guided.json", accepted_cases)
    print(f"\nDone. {len(accepted_cases)}/{TARGET} Skill-Guided cases accepted.")


if __name__ == "__main__":
    run()
