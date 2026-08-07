"""Extract enrichment fields from accepted process models and write ord_enriched.json.

Reads proc_*_enrichment.json files. For each GT-eligible resource, writes
capabilities, useCases, processNext, partOfGroups into ord_enriched.json
(which starts as a copy of ord.json). Non-GT resources stay at Clean-ORD level.

Output: data/landscape/systems/{namespace}/ord_enriched.json (updated)
        data/test_cases/design_time/logs/enrichment_log.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

PROCESSES_DIR = ROOT / "benchmark" / "test_cases" / "design_time" / "output" / "processes"
SYSTEMS_DIR = ROOT / "benchmark" / "landscape" / "systems"
ENRICHED_DIR = ROOT / "benchmark" / "landscape" / "systems_enriched"
LOG_FILE = ROOT / "benchmark" / "test_cases" / "design_time" / "logs" / "enrichment_log.json"


def load_all_enrichments() -> dict[str, dict]:
    """Returns ordId -> enrichment_fields from all accepted process models."""
    combined: dict[str, dict] = {}
    for enrich_path in sorted(PROCESSES_DIR.glob("proc_*_enrichment.json")):
        data = json.loads(enrich_path.read_text())
        process_id = data["process_id"]  # noqa: F841
        for ord_id, fields in data.get("enrichment", {}).items():
            if ord_id not in combined:
                combined[ord_id] = fields.copy()
            else:
                # merge: append capabilities/useCases, union partOfGroups
                existing = combined[ord_id]
                existing["capabilities"] = list(set(existing.get("capabilities", []) + fields.get("capabilities", [])))
                existing["useCases"] = list(set(existing.get("useCases", []) + fields.get("useCases", [])))
                existing["partOfGroups"] = existing.get("partOfGroups", []) + fields.get("partOfGroups", [])
                # processNext: keep from first process only
    return combined


def run():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    enrichments = load_all_enrichments()
    print(f"Loaded enrichment for {len(enrichments)} GT resources")

    log_entries = []
    total_enriched = 0
    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)

    for ns_dir in sorted(SYSTEMS_DIR.iterdir()):
        if not ns_dir.is_dir() or ns_dir.name == "sap.odm":
            continue

        clean = json.loads((ns_dir / "ord.json").read_text())

        # start from clean copy
        enriched = json.loads(json.dumps(clean))  # deep copy

        ns_count = 0
        for rtype_key in ("agents", "apiResources", "dataProducts"):
            for r in enriched.get(rtype_key, []):
                oid = r.get("ordId")
                if oid and oid in enrichments:
                    r.update(enrichments[oid])
                    ns_count += 1
                    log_entries.append({
                        "ordId": oid,
                        "namespace": ns_dir.name,
                        "fields_added": list(enrichments[oid].keys()),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

        out_dir = ENRICHED_DIR / ns_dir.name
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "ord_enriched.json").write_text(json.dumps(enriched, indent=2))
        total_enriched += ns_count
        print(f"  {ns_dir.name}: {ns_count} resources enriched")

    LOG_FILE.write_text(json.dumps(log_entries, indent=2))
    print(f"\nDone. {total_enriched} resources enriched → data/landscape/systems_enriched/")
    print(f"Log: {LOG_FILE}")


if __name__ == "__main__":
    run()
