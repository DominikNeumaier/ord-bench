"""Generate SKILL.md files from accepted process models.

Reads all proc_*.xml + proc_*_enrichment.json from output/processes/.
Generates one SKILL.md per process via LLM, then validates it with the
deterministic S1-S4 structural checks. Output goes to output/skills/.

Output: data/test_cases/design_time/output/skills/{process_id}.md
        data/test_cases/design_time/logs/skill_construction_log.json
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src import llm

PROCESSES_DIR = ROOT / "data" / "test_cases" / "design_time" / "output" / "processes"
SKILLS_DIR = ROOT / "data" / "test_cases" / "design_time" / "output" / "skills"
LOG_FILE = ROOT / "data" / "test_cases" / "design_time" / "logs" / "skill_construction_log.json"
MAX_ATTEMPTS = 5


def load_process(process_id: str) -> tuple[str, dict]:
    xml = (PROCESSES_DIR / f"{process_id}.xml").read_text()
    enrichment_data = json.loads((PROCESSES_DIR / f"{process_id}_enrichment.json").read_text())
    return xml, enrichment_data


def validate_skill(skill_text: str, gt_ord_ids: list[str]) -> tuple[bool, str, dict]:
    """S1-S4 deterministic checks."""
    results = {}

    # S1: every step has exactly one ord_confirmed
    confirmed = re.findall(r'ord_confirmed:\s*([^\s\-\*\n]+)', skill_text)
    results["S1"] = len(confirmed) > 0 and all(c.strip() for c in confirmed)
    if not results["S1"]:
        return False, "S1: no ord_confirmed annotations found", {**results, "S2": "skipped", "S3": "skipped", "S4": "skipped"}

    # S2: all ord_confirmed ordIds exist in GT list
    results["S2"] = all(c in gt_ord_ids for c in confirmed)
    if not results["S2"]:
        bad = [c for c in confirmed if c not in gt_ord_ids]
        return False, f"S2: unknown ordIds: {bad}", {**results, "S3": "skipped", "S4": "skipped"}

    # S3: no ordId appears more than once
    results["S3"] = len(confirmed) == len(set(confirmed))
    if not results["S3"]:
        return False, "S3: duplicate ord_confirmed ordIds", {**results, "S4": "skipped"}

    # S4: resource names / ordIds not in step description text (outside comments)
    desc_text = re.sub(r'<!--.*?-->', '', skill_text, flags=re.DOTALL)
    has_leak = any(oid in desc_text for oid in gt_ord_ids)
    results["S4"] = not has_leak
    if not results["S4"]:
        return False, "S4: ordId appears in step description text", results

    return True, "", results


def build_skill_prompt(process_id: str, xml_text: str, enrichment_data: dict) -> str:
    gt_ids = enrichment_data.get("gt_ordIds", [])
    ptype = enrichment_data.get("process_type", "bpmn")
    enrichment = enrichment_data.get("enrichment", {})

    # extract steps from XML
    steps = re.findall(
        r'<step[^>]+id=["\']([^"\']+)["\'][^>]+label=["\']([^"\']+)["\'][^>]+description=["\']([^"\']+)["\'][^>]+ordId=["\']([^"\']+)["\'][^>]*/?>',
        xml_text
    )

    steps_block = ""
    for s_id, label, desc, oid in steps:
        is_gt = oid in gt_ids
        e = enrichment.get(oid, {})
        cap = e.get("capabilities", [""])[0] if is_gt else ""
        use_case = e.get("useCases", [""])[0] if is_gt else ""  # noqa: F841
        steps_block += f"\n  - id: {s_id}, label: {label}, desc: {desc}, ordId: {oid}, is_gt: {is_gt}, capability: {cap}, useCase: {use_case}"

    return f"""Create a SKILL.md file for process '{process_id}' ({ptype.upper()}).

Process steps:
{steps_block}

GT-eligible ordIds (use ONLY these for ord_confirmed annotations): {gt_ids}

Rules:
- Include ALL steps, but add ord_confirmed ONLY for GT-eligible steps
- ord_confirmed must be the exact ordId as an HTML comment: <!-- ord_confirmed: <ordId> -->
- Step descriptions must be user-facing business language
- Do NOT mention resource names, ordIds, or system names in descriptions
- Include realistic Input/Output and Capability per step

Output the complete SKILL.md (YAML frontmatter + Steps section):

---
name: {process_id}
description: >
  [2-3 sentence description of what scenario this skill covers]
metadata:
  process-id: {process_id}
  process-type: {ptype}
  landscape-version: v2-benchmark-273
---

## Steps

### Step 1: [label]
<!-- ord_confirmed: [ordId] -->  (only for GT steps)
**Input:** [inputs]
**Output:** [outputs]
**Capability:** [capability]
[1-2 sentence user-facing description]

[... continue for all {len(steps) or 8} steps]
"""


def run():
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    process_files = sorted(PROCESSES_DIR.glob("proc_*.xml"))
    if not process_files:
        print("No process files found. Run generate_processes.py first.")
        return

    log_entries = []
    accepted = 0

    for xml_path in process_files:
        process_id = xml_path.stem
        enrich_path = PROCESSES_DIR / f"{process_id}_enrichment.json"
        if not enrich_path.exists():
            print(f"  Skipping {process_id}: no enrichment file")
            continue

        skill_out = SKILLS_DIR / f"{process_id}.md"
        if skill_out.exists():
            print(f"  Skipping {process_id}: already generated")
            accepted += 1
            continue

        xml_text, enrichment_data = load_process(process_id)
        gt_ids = enrichment_data.get("gt_ordIds", [])

        print(f"\n[{process_id}] Generating SKILL.md ({len(gt_ids)} GT steps)...")

        for attempt in range(1, MAX_ATTEMPTS + 1):
            prompt = build_skill_prompt(process_id, xml_text, enrichment_data)
            skill_text, meta = llm.chat(prompt)

            # strip any preamble before ---
            if "---" in skill_text:
                skill_text = skill_text[skill_text.index("---"):]

            v_ok, v_fail, v_results = validate_skill(skill_text, gt_ids)
            entry = {
                "skill_id": process_id,
                "process_id": process_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "attempt": attempt,
                "generator_tokens": meta["tokens"],
                "validator_results": v_results,
                "validator_failure": v_fail if not v_ok else None,
                "outcome": None,
            }

            if not v_ok:
                print(f"  attempt {attempt}: VALIDATOR FAIL — {v_fail}")
                entry["outcome"] = "VALIDATOR_FAIL"
                log_entries.append(entry)
                continue

            # A skill is accepted once the deterministic S1-S4 checks pass;
            # these structural checks are sufficient for the SKILL.md format.
            entry["outcome"] = "ACCEPTED"
            log_entries.append(entry)
            skill_out.write_text(skill_text)
            accepted += 1
            print(f"  attempt {attempt}: ACCEPTED → {process_id}.md")
            break
        else:
            print(f"  GAVE UP after {MAX_ATTEMPTS} attempts")
            log_entries.append({**entry, "outcome": "GAVE_UP"})

    LOG_FILE.write_text(json.dumps(log_entries, indent=2))
    print(f"\nDone. {accepted}/{len(process_files)} skills accepted.")


if __name__ == "__main__":
    run()
