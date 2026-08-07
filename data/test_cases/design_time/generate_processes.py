"""Generate 30 BPMN/CMMN process models (15+15) for design-time evaluation.

Each model: 8 steps, 4 GT-eligible + 4 non-GT resources, ≥3 namespaces,
≥1 agent + ≥1 apiResource. Generator produces process XML + enrichment fields
in one call. Validator (V1-V6) runs first, Judge (J1-J6) only if validator passes.

Output: data/test_cases/design_time/output/processes/{id}.xml
        data/test_cases/design_time/logs/process_construction_log.json
"""
from __future__ import annotations

import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.core import llm

LANDSCAPE_DIR = ROOT / "data" / "landscape" / "systems"
AMBIGUITY_REPORT = ROOT / "data" / "ambiguity" / "landscape_ambiguity_report.json"
OUTPUT_DIR = ROOT / "data" / "test_cases" / "design_time" / "output" / "processes"
LOG_FILE = ROOT / "data" / "test_cases" / "design_time" / "logs" / "process_construction_log.json"

TARGET_BPMN = 15
TARGET_CMMN = 15
STEPS_PER_MODEL = 8
GT_PER_MODEL = 4
MAX_ATTEMPTS = 8
RANDOM_SEED = 42


def load_landscape() -> tuple[dict[str, dict], set[str]]:
    """Returns (ordId -> resource_dict, gt_eligible_set)."""
    report = json.loads(AMBIGUITY_REPORT.read_text())
    gt_ids = {r["ordId"] for r in report["resources"] if r.get("ground_truth_eligible")}

    resources = {}
    for ns_dir in LANDSCAPE_DIR.iterdir():
        if not ns_dir.is_dir() or ns_dir.name == "sap.odm":
            continue
        data = json.loads((ns_dir / "ord.json").read_text())
        ns = ns_dir.name
        for rtype, key in [("agent", "agents"), ("apiResource", "apiResources"), ("dataProduct", "dataProducts")]:
            for r in data.get(key, []):
                r["_rtype"] = rtype
                r["_ns"] = ns
                resources[r["ordId"]] = r
    return resources, gt_ids


def select_resources(resources: dict, gt_ids: set, used_gt: set, rng: random.Random) -> tuple[list, list, str] | None:
    """Pick 4 GT + 4 non-GT resources. Returns (gt_list, non_gt_list, process_type) or None."""
    gt_pool = [r for oid, r in resources.items() if oid in gt_ids and oid not in used_gt]
    non_gt_pool = [r for oid, r in resources.items() if oid not in gt_ids]

    if len(gt_pool) < GT_PER_MODEL:
        gt_pool = [r for oid, r in resources.items() if oid in gt_ids]

    for _ in range(50):
        gt_sel = rng.sample(gt_pool, GT_PER_MODEL)
        non_gt_sel = rng.sample(non_gt_pool, STEPS_PER_MODEL - GT_PER_MODEL)
        all_sel = gt_sel + non_gt_sel

        namespaces = {r["_ns"] for r in all_sel}
        rtypes = {r["_rtype"] for r in all_sel}
        if len(namespaces) < 3 or "agent" not in rtypes or "apiResource" not in rtypes:
            continue

        # BPMN for operational/structured, CMMN for knowledge-intensive
        agent_count = sum(1 for r in all_sel if r["_rtype"] == "agent")
        ptype = "cmmn" if agent_count >= 4 else "bpmn"
        return gt_sel, non_gt_sel, ptype

    return None


def validate(xml_text: str, gt_ids_sel: list[str], non_gt_ids_sel: list[str], resources: dict) -> tuple[bool, str, dict]:
    """V1-V6 deterministic checks. Returns (ok, failure_msg, results_dict)."""
    results = {f"V{i}": None for i in range(1, 7)}

    try:
        ET.fromstring(xml_text)
    except ET.ParseError as e:
        return False, f"XML parse error: {e}", results

    step_ords = re.findall(r'ordId=["\']([^"\']+)["\']', xml_text)

    results["V1"] = all(oid in resources for oid in step_ords)
    if not results["V1"]:
        missing = [o for o in step_ords if o not in resources]
        return False, f"V1: unknown ordIds: {missing[:3]}", {**results, **{f"V{i}": "skipped" for i in range(2, 7)}}

    results["V2"] = len(step_ords) == len(set(step_ords))
    if not results["V2"]:
        return False, "V2: duplicate ordIds in process", {**results, **{f"V{i}": "skipped" for i in range(3, 7)}}

    found_gt = [o for o in step_ords if o in gt_ids_sel]
    found_non_gt = [o for o in step_ords if o in non_gt_ids_sel]
    results["V3"] = len(found_gt) == GT_PER_MODEL and len(found_non_gt) == (STEPS_PER_MODEL - GT_PER_MODEL)
    if not results["V3"]:
        return False, f"V3: {len(found_gt)} GT + {len(found_non_gt)} non-GT, need {GT_PER_MODEL}/{STEPS_PER_MODEL - GT_PER_MODEL}", {**results, **{f"V{i}": "skipped" for i in range(4, 7)}}

    step_ns = {resources[o]["_ns"] for o in step_ords if o in resources}
    results["V4"] = len(step_ns) >= 3
    if not results["V4"]:
        return False, f"V4: only {len(step_ns)} namespaces, need ≥3", {**results, **{"V5": "skipped", "V6": "skipped"}}

    step_rtypes = {resources[o]["_rtype"] for o in step_ords if o in resources}
    results["V5"] = "agent" in step_rtypes and "apiResource" in step_rtypes
    if not results["V5"]:
        return False, f"V5: missing agent or apiResource (found: {step_rtypes})", {**results, "V6": "skipped"}

    results["V6"] = len(step_ords) == STEPS_PER_MODEL
    if not results["V6"]:
        return False, f"V6: {len(step_ords)} steps, need {STEPS_PER_MODEL}", results

    return True, "", results


def judge(xml_text: str, enrichment: dict, process_type: str) -> tuple[bool, dict, str, int]:
    """J1-J6 LLM checks. Returns (accepted, results, response_text, tokens)."""
    sys_prompt = (
        "You are a quality judge for a synthetic enterprise benchmark. "
        "Be pragmatic: accept processes that are plausible and well-structured, "
        "even if imperfect. Reject only clear failures. Answer ONLY with valid JSON."
    )
    j6_note = "J6: true if enrichment is non-empty and capabilities/useCases match step actions" if enrichment else "J6: true (no enrichment to check)"
    user_prompt = f"""Review this {process_type.upper()} process model for a retrieval benchmark.

PROCESS XML:
{xml_text[:4000]}

ENRICHMENT:
{json.dumps(enrichment, indent=2)[:1500] if enrichment else "(none provided yet)"}

Rate each criterion — be generous, this is a synthetic benchmark:
{{
  "J1": true/false,  // process type fits: BPMN=ordered steps, CMMN=adaptive/case
  "J2": true/false,  // step labels describe business activities (not "call API X")
  "J3": true/false,  // step descriptions state a business need (not "this agent does X")
  "J4": true/false,  // resources are plausibly matched to their activities
  "J5": true/false,  // steps together form a coherent enterprise scenario
  "J6": true/false,  // {j6_note}
  "accepted": true/false,  // true if J1+J2+J3+J4+J5 all pass (J6 optional)
  "reason": "one sentence only if rejected"
}}"""

    text, meta = llm.chat(user_prompt, system=sys_prompt)
    tokens = meta["tokens"]

    try:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        data = json.loads(m.group()) if m else {}
        results = {f"J{i}": data.get(f"J{i}") for i in range(1, 7)}
        accepted = bool(data.get("accepted", False))
        return accepted, results, text, tokens
    except Exception:
        return False, {f"J{i}": None for i in range(1, 7)}, text, tokens


def build_prompt(gt_resources: list, non_gt_resources: list, process_type: str) -> str:
    def fmt(r):
        ets = r.get("relatedEntityTypes") or r.get("exposedEntityTypes") or r.get("entityTypes") or []
        et_ids = [e["ordId"] if isinstance(e, dict) else e for e in ets]
        return f'  ordId: {r["ordId"]}\n  title: {r["title"]}\n  type: {r["_rtype"]}\n  entityTypes: {et_ids}\n  lob: {r.get("lineOfBusiness", [])}'

    gt_block = "\n\n".join(fmt(r) for r in gt_resources)
    non_gt_block = "\n\n".join(fmt(r) for r in non_gt_resources)

    return f"""Create a coherent 8-step {process_type.upper()} enterprise process model using EXACTLY these resources.

GT-ELIGIBLE RESOURCES (4 steps, these are the evaluation targets):
{gt_block}

NON-GT RESOURCES (4 steps, supporting roles):
{non_gt_block}

Rules:
- Exactly 8 steps, one step per resource, in logical enterprise order
- Activity labels: business activities (e.g. "Diagnose equipment failure"), NOT resource names
- Activity descriptions: describe the business need, NOT the resource type
- The process must tell a coherent real enterprise scenario
- For CMMN: use case-driven/conditional structure; for BPMN: sequential/structured

Output TWO parts:

PART 1 - Process XML:
<process id="proc_[short_name]_v1" type="{process_type}">
  <step id="s1" label="[activity label]"
        description="[business need in 1 sentence]"
        ordId="[ordId]"
        capability="[verb-noun, e.g. diagnose-equipment]"
        useCase="[1 sentence user-facing context]"/>
  ... (8 steps total)
  <sequenceFlow from="s1" to="s2"/>
  ... (connect all steps in order)
</process>

PART 2 - Enrichment (GT resources only, JSON):
{{
  "[ordId_of_gt_resource]": {{
    "capabilities": ["verb-noun"],
    "useCases": ["1 sentence"],
    "processNext": ["[ordId_of_next_gt_resource_or_empty]"],
    "partOfGroups": [{{"groupId": "proc_[short_name]_v1", "groupTypeId": "{process_type}"}}]
  }}
}}
"""


def parse_generator_output(text: str, gt_ids: set) -> tuple[str, dict]:
    """Extract XML and enrichment JSON from generator response."""
    xml_match = re.search(r'(<process\b.*?</process>)', text, re.DOTALL | re.IGNORECASE)
    xml_text = xml_match.group(1) if xml_match else ""

    # find JSON block (may be wrapped in ```json ... ```)
    json_candidates = re.findall(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if not json_candidates:
        json_candidates = re.findall(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', text, re.DOTALL)

    enrichment = {}
    for candidate in reversed(json_candidates):  # last block most likely enrichment
        try:
            parsed = json.loads(candidate)
            # enrichment block has ordId-like keys
            if any(":" in k for k in parsed.keys()):
                enrichment = {k: v for k, v in parsed.items() if k in gt_ids}
                if enrichment:
                    break
        except Exception:
            continue

    return xml_text, enrichment


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    print("Loading landscape...")
    resources, gt_ids = load_landscape()
    rng = random.Random(RANDOM_SEED)

    log_entries = []
    accepted_bpmn = 0
    accepted_cmmn = 0
    used_gt: set[str] = set()

    print(f"Landscape: {len(resources)} resources, {len(gt_ids)} GT-eligible")
    print(f"Target: {TARGET_BPMN} BPMN + {TARGET_CMMN} CMMN")

    model_index = 0
    while accepted_bpmn < TARGET_BPMN or accepted_cmmn < TARGET_CMMN:
        need_bpmn = accepted_bpmn < TARGET_BPMN
        need_cmmn = accepted_cmmn < TARGET_CMMN
        model_index += 1

        sel = select_resources(resources, gt_ids, used_gt, rng)
        if sel is None:
            print("  Could not select valid resource set, retrying with full GT pool...")
            used_gt.clear()
            continue

        gt_sel, non_gt_sel, suggested_type = sel
        # override type if we only need one kind
        if need_bpmn and not need_cmmn:
            ptype = "bpmn"
        elif need_cmmn and not need_bpmn:
            ptype = "cmmn"
        else:
            ptype = suggested_type

        gt_ids_sel = [r["ordId"] for r in gt_sel]
        non_gt_ids_sel = [r["ordId"] for r in non_gt_sel]
        process_id = f"proc_{model_index:03d}"

        print(f"\n[{process_id}] {ptype.upper()} | GT: {gt_ids_sel[:2]}...")

        for attempt in range(1, MAX_ATTEMPTS + 1):
            prompt = build_prompt(gt_sel, non_gt_sel, ptype)
            raw, meta = llm.chat(prompt)
            xml_text, enrichment = parse_generator_output(raw, set(gt_ids_sel))

            v_ok, v_fail, v_results = validate(xml_text, gt_ids_sel, non_gt_ids_sel, resources)

            entry = {
                "process_id": process_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "attempt": attempt,
                "process_type": ptype,
                "resource_pool": {"gt": gt_ids_sel, "non_gt": non_gt_ids_sel},
                "generator_tokens": meta["tokens"],
                "validator_results": v_results,
                "validator_failure": v_fail if not v_ok else None,
                "judge_results": None,
                "judge_response": None,
                "judge_tokens": 0,
                "outcome": None,
            }

            if not v_ok:
                print(f"  attempt {attempt}: VALIDATOR FAIL — {v_fail}")
                entry["outcome"] = "VALIDATOR_FAIL"
                log_entries.append(entry)
                continue

            j_ok, j_results, j_response, j_tokens = judge(xml_text, enrichment, ptype)
            entry["judge_results"] = j_results
            entry["judge_response"] = j_response
            entry["judge_tokens"] = j_tokens

            if not j_ok:
                print(f"  attempt {attempt}: JUDGE FAIL")
                entry["outcome"] = "JUDGE_FAIL"
                log_entries.append(entry)
                continue

            # ACCEPTED
            entry["outcome"] = "ACCEPTED"
            log_entries.append(entry)

            out_path = OUTPUT_DIR / f"{process_id}.xml"
            out_path.write_text(xml_text)

            # save enrichment alongside
            enrich_path = OUTPUT_DIR / f"{process_id}_enrichment.json"
            enrich_path.write_text(json.dumps({
                "process_id": process_id,
                "process_type": ptype,
                "gt_ordIds": gt_ids_sel,
                "enrichment": enrichment,
            }, indent=2))

            used_gt.update(gt_ids_sel)
            if ptype == "bpmn":
                accepted_bpmn += 1
            else:
                accepted_cmmn += 1

            print(f"  attempt {attempt}: ACCEPTED → {process_id}.xml (BPMN:{accepted_bpmn} CMMN:{accepted_cmmn})")
            break
        else:
            print(f"  GAVE UP after {MAX_ATTEMPTS} attempts")
            log_entries.append({**entry, "outcome": "GAVE_UP"})

    LOG_FILE.write_text(json.dumps(log_entries, indent=2))
    print(f"\nDone. {accepted_bpmn} BPMN + {accepted_cmmn} CMMN accepted.")
    print(f"Log: {LOG_FILE}")


if __name__ == "__main__":
    run()
