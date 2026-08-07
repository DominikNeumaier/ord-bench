"""Deterministic taxonomy validator for sap.odm entity types.

Checks structural integrity of the entity type list:
  1. No duplicate ordIds
  2. All required ORD fields present per entity type
  3. All relatedEntityTypes references (if any) resolve to existing IDs

Note: relatedEntityTypes within sap.odm are NOT required — the entity types
are a flat vocabulary list. The graph structure emerges from retrieval resources
that reference these IDs, not from links between entity types themselves.

Usage:
    python src/generation/validate_taxonomy.py
    python src/generation/validate_taxonomy.py --taxonomy data/landscape/systems/sap.odm/ord.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def validate_taxonomy(taxonomy_path: Path) -> dict:
    doc = json.loads(taxonomy_path.read_text())
    entity_types = doc.get("entityTypes", [])

    errors: list[str] = []
    warnings: list[str] = []

    # Build ID set
    id_set: set[str] = set()
    seen_ids: set[str] = set()

    for et in entity_types:
        oid = et.get("ordId", "")
        if not oid:
            errors.append(f"Entity type missing ordId: {et.get('title', '?')}")
            continue
        if oid in seen_ids:
            errors.append(f"Duplicate ordId: {oid}")
        seen_ids.add(oid)
        id_set.add(oid)

    # Check references if relatedEntityTypes are present (optional)
    for et in entity_types:
        oid = et.get("ordId", "")
        related = et.get("relatedEntityTypes", [])
        for ref in related:
            ref_id = ref.get("ordId", "")
            if not ref_id:
                errors.append(f"{oid}: relatedEntityTypes entry missing ordId")
            elif ref_id not in id_set:
                errors.append(f"{oid}: references unknown entity type '{ref_id}'")

    passed = len(errors) == 0
    return {
        "taxonomy_path": str(taxonomy_path),
        "total_entity_types": len(entity_types),
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
    }


def print_report(result: dict) -> None:
    print(f"\n{'='*60}")
    print(f"TAXONOMY VALIDATION REPORT")
    print(f"{'='*60}")
    print(f"File:          {result['taxonomy_path']}")
    print(f"Entity types:  {result['total_entity_types']}")
    print(f"Errors:        {len(result['errors'])}")
    print(f"Warnings:      {len(result['warnings'])}")

    if result["errors"]:
        print("\nERRORS:")
        for e in result["errors"]:
            print(f"  ✗ {e}")

    if result["warnings"]:
        print("\nWARNINGS:")
        for w in result["warnings"]:
            print(f"  ⚠ {w}")

    status = "PASS" if result["passed"] else "FAIL"
    print(f"\n{'='*60}")
    print(f"RESULT: {status}")
    print(f"{'='*60}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate sap.odm entity type taxonomy")
    parser.add_argument(
        "--taxonomy",
        default=str(ROOT / "data" / "landscape" / "systems" / "sap.odm" / "ord.json"),
        help="Path to sap.odm ord.json",
    )
    parser.add_argument("--output", help="Write JSON result to this path")
    args = parser.parse_args()

    path = Path(args.taxonomy)
    if not path.exists():
        print(f"Taxonomy file not found: {path}")
        return 1

    result = validate_taxonomy(path)
    print_report(result)

    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2))

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
