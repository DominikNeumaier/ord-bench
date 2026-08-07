"""Extract design-time test cases from accepted process models.

Reads proc_*.xml files. For each step, creates one retrieval case:
  input:  step label + " — " + step description
  output: expected_ordId

Output: data/test_cases/design_time/output/activity_cases.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

PROCESSES_DIR = ROOT / "benchmark" / "test_cases" / "design_time" / "output" / "processes"
OUTPUT_FILE = ROOT / "benchmark" / "test_cases" / "design_time" / "output" / "activity_cases.json"


def run():
    cases = []

    for xml_path in sorted(PROCESSES_DIR.glob("proc_*.xml")):
        process_id = xml_path.stem
        enrich_path = PROCESSES_DIR / f"{process_id}_enrichment.json"
        gt_ids = set()
        if enrich_path.exists():
            gt_ids = set(json.loads(enrich_path.read_text()).get("gt_ordIds", []))

        xml_text = xml_path.read_text()
        steps = re.findall(
            r'<step[^>]+id=["\']([^"\']+)["\'][^>]+label=["\']([^"\']+)["\'][^>]+description=["\']([^"\']+)["\'][^>]+ordId=["\']([^"\']+)["\'][^>]*/?>',
            xml_text
        )

        for i, (step_id, label, description, ord_id) in enumerate(steps, 1):
            cases.append({
                "case_id": f"{process_id}_s{i:02d}",
                "process_id": process_id,
                "step_index": i,
                "step_id": step_id,
                "input": f"{label} — {description}",
                "expected_ordId": ord_id,
                "is_gt": ord_id in gt_ids,
            })

    OUTPUT_FILE.write_text(json.dumps(cases, indent=2))
    gt_count = sum(1 for c in cases if c["is_gt"])
    print(f"Extracted {len(cases)} cases ({gt_count} GT, {len(cases)-gt_count} non-GT) from {len(set(c['process_id'] for c in cases))} processes.")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
