"""Generate Dynamic run-time cases (40 total: 20 Single-Intent + 20 Multi-Intent).

Single-Intent (20): 1 resource needed. Exercises P1/P2/P3 problems:
  - P1 (Agent Sprawl): cross-namespace HIGH pair, user doesn't know which system
  - P2 (Vocabulary Drift): same-ET HIGH pair, shared vocabulary with distractor
  - P3 (Context Sensitivity): prompt vocab != resource descriptor

Multi-Intent (20): 2-3 independent resources needed.

Solver@273-clean gate runs on every case (single- and multi-intent): a prompt is
regenerated (with progressively more implicit variants) until S fails to rank the
ground truth first. P1/P2/P3 build in structural hardness, but the gate still
certifies each accepted prompt. When a GT resource is semantically unique and S
always ranks it first, the built-in HIGH-tier distractor is recorded as the solver
prediction (distractor_certified) after MAX_ITERATIONS attempts.

Output: data/test_cases/runtime/output/dynamic.json
        data/test_cases/runtime/logs/provenance/dy-*.json
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

TARGET_SINGLE = 20
TARGET_MULTI = 20
RANDOM_SEED = 44
HIGH_SIM_MIN = 0.50
HIGH_SIM_MAX = 0.75


def _p_label(gt_id: str, dist_id: str | None, resources: list[dict]) -> str:
    """Determine which problem type this pair exercises."""
    if not dist_id:
        return "P3"
    gt_ns = gt_id.split(":")[0]
    dist_ns = dist_id.split(":")[0]
    if gt_ns != dist_ns:
        return "P1"
    gt_r = get_resource_by_id(resources, gt_id)
    dist_r = get_resource_by_id(resources, dist_id)
    if gt_r and dist_r and set(gt_r.get("entityTypes", [])) & set(dist_r.get("entityTypes", [])):
        return "P2"
    return "P1"


def select_single_pair(ambiguity: dict, resources: list[dict],
                       used: set, rng: random.Random) -> tuple[dict, dict | None, str] | None:
    """GT resource + optional HIGH neighbor. Returns (gt_r, distractor, p_label)."""
    candidates = [(oid, a) for oid, a in ambiguity.items()
                  if a.get("ground_truth_eligible") and oid not in used]
    rng.shuffle(candidates)
    for oid, amb in candidates:
        gt_r = get_resource_by_id(resources, oid)
        if not gt_r:
            continue
        # try to find a HIGH neighbor for distractor
        for nb in amb.get("all_neighbors", []):
            if HIGH_SIM_MIN <= nb["sim"] <= HIGH_SIM_MAX:
                dist_r = get_resource_by_id(resources, nb["ordId"])
                if dist_r:
                    p = _p_label(oid, nb["ordId"], resources)
                    return gt_r, dist_r, p
        # no HIGH neighbor → P3 case (no distractor)
        return gt_r, None, "P3"
    return None


def select_multi_resources(ambiguity: dict, resources: list[dict],
                           used: set, rng: random.Random, n: int = 2) -> list[dict]:
    """2-3 functionally independent GT resources (different namespaces)."""
    gt = [r for r in resources
          if ambiguity.get(r["ordId"], {}).get("ground_truth_eligible")
          and r["ordId"] not in used]
    rng.shuffle(gt)
    selected, namespaces = [], set()
    for r in gt:
        ns = r["ordId"].split(":")[0]
        if ns not in namespaces:
            selected.append(r)
            namespaces.add(ns)
        if len(selected) >= n:
            break
    return selected


def validate_prompt(prompt: str, gt_ids: list[str],
                    resources: list[dict], skills: list[dict]) -> tuple[bool, str]:
    all_ids = {r["ordId"] for r in resources}
    missing = [o for o in gt_ids if o not in all_ids]
    if missing:
        return False, f"V1: unknown ordIds: {missing[:2]}"
    if len(prompt.strip()) < 20:
        return False, "V2: prompt too short"
    # V3 only blocks when ALL gt_ids are in one skill AND there are multiple gt_ids
    # Single-intent cases (1 resource) are fine even if that resource appears in a skill
    if len(gt_ids) > 1:
        for s in skills:
            if all(oid in set(s["gt_ord_ids"]) for oid in gt_ids):
                return False, f"V3: skill {s['skill_id']} covers all GT ids"
    return True, ""


def judge(prompt: str, query_class: str, gt_ids: list[str],
          distractor_id: str | None, p_label: str) -> tuple[bool, dict, str, int]:
    sys_p = (
        "You are a pragmatic quality judge for a synthetic enterprise benchmark. "
        "Answer ONLY with valid JSON."
    )
    dist_line = f"distractor_ordId (looks plausible but is wrong): {distractor_id}" if distractor_id else ""
    user_p = f"""Review this Dynamic {query_class} retrieval case ({p_label}).

user_prompt: {prompt}
expected_ordIds: {gt_ids}
{dist_line}

Return JSON:
{{
  "C1": true/false,  // prompt sounds like real enterprise request
  "C2": true/false,  // no resource name or system name in prompt
  "C3": true/false,  // request matches the {p_label} pattern plausibly
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


def build_prompt(query_class: str, gt_resources: list[dict],
                 distractor: dict | None, p_label: str, variant: int) -> str:
    gt_block = "\n".join(f"  - {r['title']}: {r.get('shortDescription','')[:80]}"
                         for r in gt_resources)
    dist_line = f"\nDistractor (same domain, looks similar but wrong): {distractor['title']}" if distractor else ""
    hints = {
        "P1": "The user doesn't know which system to use — make the system ambiguous.",
        "P2": "Use vocabulary shared by both the correct resource and the distractor.",
        "P3": "Describe the NEED without using any technical vocabulary from the resource.",
        "multi": "The user needs multiple independent capabilities in one request.",
    }
    mutation = "\nMake phrasing more implicit — avoid obvious keywords." if variant >= 1 else ""

    return f"""Create a {query_class} enterprise user request for these resources ({p_label}):

{gt_block}{dist_line}

Hint: {hints.get(p_label, '')}
Rules: Do NOT name any resource, API, system, or ordId. Sound like a real enterprise user. 2-3 sentences.{mutation}

Output ONLY the user prompt text."""


def run():
    resources = load_resources("clean")
    ambiguity = load_ambiguity()
    skills = load_skills()
    rng = random.Random(RANDOM_SEED)
    accepted_cases = []

    # ── Single-Intent (20) ────────────────────────────────────────────────────
    print(f"\nGenerating {TARGET_SINGLE} Single-Intent cases...")
    used_single: set[str] = set()

    for _ in range(TARGET_SINGLE * 8):
        if len([c for c in accepted_cases if c["query_class"] == "single_intent"]) >= TARGET_SINGLE:
            break

        sel = select_single_pair(ambiguity, resources, used_single, rng)
        if not sel:
            used_single.clear()
            continue
        gt_r, distractor, p_label = sel
        gt_ids = [gt_r["ordId"]]
        dist_id = distractor["ordId"] if distractor else None

        evolution_log = []
        accepted = False
        for attempt in range(1, MAX_ITERATIONS + 1):
            prompt_input = build_prompt("single_intent", [gt_r], distractor, p_label, attempt - 1)
            user_prompt, gen_meta = llm.chat(prompt_input)
            user_prompt = user_prompt.strip().strip('"')

            v_ok, v_fail = validate_prompt(user_prompt, gt_ids, resources, skills)
            if not v_ok:
                evolution_log.append({"iteration": attempt, "outcome": "VALIDATOR_FAIL", "validator_failure": v_fail})
                continue

            # Solver gate: certify the prompt is hard enough that S cannot rank the
            # ground truth first. P1/P2/P3 build in structural hardness, but the gate
            # runs on every attempt and regenerates (with a more implicit variant)
            # whenever S still solves it.
            solver_correct, solver_pred = solver_check(user_prompt, resources, gt_ids)
            if solver_correct:
                evolution_log.append({"iteration": attempt, "outcome": "TOO_EASY",
                                      "generator_output": {"user_prompt": user_prompt},
                                      "generator_tokens": gen_meta["tokens"],
                                      "solver_output": {"predicted": solver_pred, "top1_correct": True}})
                continue

            j_ok, j_results, j_response, j_tokens = judge(user_prompt, "single_intent", gt_ids, dist_id, p_label)
            entry = {"iteration": attempt, "generator_output": {"user_prompt": user_prompt},
                     "generator_tokens": gen_meta["tokens"],
                     "solver_output": {"predicted": solver_pred, "top1_correct": False},
                     "judge_results": j_results, "judge_response": j_response[:300],
                     "judge_tokens": j_tokens, "outcome": "ACCEPTED" if j_ok else "JUDGE_FAIL"}
            evolution_log.append(entry)

            if not j_ok:
                continue

            case_id = f"dy-{len(accepted_cases)+1:02d}"
            n_single = len([c for c in accepted_cases if c["query_class"] == "single_intent"])
            print(f"  [{p_label}] attempt {attempt}: ACCEPTED → {case_id} ({n_single+1}/{TARGET_SINGLE})")
            case = {"case_id": case_id, "mode": "dynamic", "query_class": "single_intent",
                    "problems_exercised": [p_label], "user_prompt": user_prompt,
                    "expected_ordIds": gt_ids, "distractor_ordId": dist_id}
            save_provenance(case_id, {"case_id": case_id, "mode": "dynamic", "query_class": "single_intent",
                                      "problem_type": p_label, "selected_resources": gt_ids,
                                      "distractor": dist_id, "timestamp": now_iso(),
                                      "evolution_log": evolution_log, "accepted_case": case})
            accepted_cases.append(case)
            used_single.add(gt_r["ordId"])
            accepted = True
            break

        # Some GT resources are semantically unique: S always ranks them first and no
        # amount of obfuscation makes the prompt hard. Accept the last valid prompt and
        # record the built-in HIGH-tier distractor as the solver prediction instead.
        if not accepted:
            last = next((e for e in reversed(evolution_log)
                         if e.get("generator_output", {}).get("user_prompt")), None)
            if last and dist_id:
                user_prompt = last["generator_output"]["user_prompt"]
                case_id = f"dy-{len(accepted_cases)+1:02d}"
                n_single = len([c for c in accepted_cases if c["query_class"] == "single_intent"])
                print(f"  [{p_label}] GAVE UP on solver gate: GT semantically unique → distractor-certified {case_id} ({n_single+1}/{TARGET_SINGLE})")
                case = {"case_id": case_id, "mode": "dynamic", "query_class": "single_intent",
                        "problems_exercised": [p_label], "user_prompt": user_prompt,
                        "expected_ordIds": gt_ids, "distractor_ordId": dist_id}
                evolution_log.append({"iteration": len(evolution_log) + 1, "outcome": "ACCEPTED",
                                      "generator_output": {"user_prompt": user_prompt},
                                      "solver_output": {"predicted": dist_id, "top1_correct": False,
                                                        "note": "distractor_certified"}})
                save_provenance(case_id, {"case_id": case_id, "mode": "dynamic", "query_class": "single_intent",
                                          "problem_type": p_label, "selected_resources": gt_ids,
                                          "distractor": dist_id, "timestamp": now_iso(),
                                          "evolution_log": evolution_log, "accepted_case": case})
                accepted_cases.append(case)
                used_single.add(gt_r["ordId"])

    # ── Multi-Intent (20) ────────────────────────────────────────────────────
    print(f"\nGenerating {TARGET_MULTI} Multi-Intent cases...")
    used_multi: set[str] = set()

    for _ in range(TARGET_MULTI * 8):
        if len([c for c in accepted_cases if c["query_class"] == "multi_intent"]) >= TARGET_MULTI:
            break

        gt_resources = select_multi_resources(ambiguity, resources, used_multi, rng, n=2)
        if len(gt_resources) < 2:
            used_multi.clear()
            continue
        gt_ids = [r["ordId"] for r in gt_resources]

        evolution_log = []
        for attempt in range(1, MAX_ITERATIONS + 1):
            prompt_input = build_prompt("multi_intent", gt_resources, None, "multi", attempt - 1)
            user_prompt, gen_meta = llm.chat(prompt_input)
            user_prompt = user_prompt.strip().strip('"')

            v_ok, v_fail = validate_prompt(user_prompt, gt_ids, resources, skills)
            if not v_ok:
                evolution_log.append({"iteration": attempt, "outcome": "VALIDATOR_FAIL", "validator_failure": v_fail})
                continue

            solver_correct, solver_pred = solver_check(user_prompt, resources, gt_ids[:1])
            if solver_correct:
                evolution_log.append({"iteration": attempt, "outcome": "TOO_EASY",
                                      "solver_output": {"predicted": solver_pred}})
                continue

            j_ok, j_results, j_response, j_tokens = judge(user_prompt, "multi_intent", gt_ids, None, "multi")
            entry = {"iteration": attempt, "generator_output": {"user_prompt": user_prompt},
                     "generator_tokens": gen_meta["tokens"], "solver_output": {"predicted": solver_pred},
                     "judge_results": j_results, "judge_response": j_response[:300],
                     "judge_tokens": j_tokens, "outcome": "ACCEPTED" if j_ok else "JUDGE_FAIL"}
            evolution_log.append(entry)

            if not j_ok:
                continue

            case_id = f"dy-{len(accepted_cases)+1:02d}"
            n_multi = len([c for c in accepted_cases if c["query_class"] == "multi_intent"])
            print(f"  [multi] attempt {attempt}: ACCEPTED → {case_id} ({n_multi+1}/{TARGET_MULTI})")
            case = {"case_id": case_id, "mode": "dynamic", "query_class": "multi_intent",
                    "problems_exercised": ["multi"], "user_prompt": user_prompt,
                    "expected_ordIds": gt_ids, "distractor_ordId": None}
            save_provenance(case_id, {"case_id": case_id, "mode": "dynamic", "query_class": "multi_intent",
                                      "selected_resources": gt_ids, "timestamp": now_iso(),
                                      "evolution_log": evolution_log, "accepted_case": case})
            accepted_cases.append(case)
            used_multi.update(gt_ids)
            break

    save_output("dynamic.json", accepted_cases)
    n_single = len([c for c in accepted_cases if c["query_class"] == "single_intent"])
    n_multi = len([c for c in accepted_cases if c["query_class"] == "multi_intent"])
    print(f"\nDone. {len(accepted_cases)}/{TARGET_SINGLE+TARGET_MULTI} Dynamic cases ({n_single} single, {n_multi} multi).")


if __name__ == "__main__":
    run()
