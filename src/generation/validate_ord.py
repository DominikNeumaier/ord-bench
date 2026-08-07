"""ORD Document Validator.

Deterministic, no LLM. Checks every resource in a landscape against
the ORD spec rules defined in ord_spec_rules.json.

Usage:
    python src/generation/validate_ord.py
    python src/generation/validate_ord.py --landscape data/landscape/systems
    python src/generation/validate_ord.py --file path/to/ord.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RULES_PATH = Path(__file__).resolve().parent / "ord_spec_rules.json"

RESOURCE_KEY_TO_TYPE = {
    "agents":                 "agent",
    "apiResources":           "apiResource",
    "dataProducts":           "dataProduct",
    "eventResources":         "eventResource",
    "integrationDependencies": "integrationDependency",
    "packages":               "package",
    "products":               "product",
    "entityTypes":            "entityType",
    "consumptionBundles":     "consumptionBundle",
    "capabilities":           "capability",
}


def load_rules() -> dict:
    return json.loads(RULES_PATH.read_text())


def check_required_fields(resource: dict, rtype: str, rules: dict) -> list[str]:
    """Return list of error messages for missing required fields."""
    errors = []
    type_rules = rules.get(rtype, {})
    for field in type_rules.get("required", []):
        val = resource.get(field)
        if val is None or val == "" or val == []:
            errors.append(f"MISSING required field '{field}'")
    return errors


def check_ordid_pattern(resource: dict, rtype: str, rules: dict) -> list[str]:
    """Check ordId format matches expected pattern for resource type."""
    errors = []
    patterns = rules.get("ordId_patterns", {})
    pattern = patterns.get(rtype)
    if not pattern:
        return []
    ordid = resource.get("ordId", "")
    if ordid and not re.match(pattern, ordid):
        errors.append(f"INVALID ordId format '{ordid}' for type '{rtype}' (expected pattern: {pattern})")
    return errors


def check_enum_fields(resource: dict, rtype: str, rules: dict) -> list[str]:
    """Check enum fields have valid values."""
    errors = []
    enums = rules.get("enum_values", {})

    if "visibility" in resource:
        valid = enums.get("visibility", [])
        if resource["visibility"] not in valid:
            errors.append(f"INVALID visibility '{resource['visibility']}' (allowed: {valid})")

    if "releaseStatus" in resource:
        valid = enums.get("releaseStatus", [])
        if resource["releaseStatus"] not in valid:
            errors.append(f"INVALID releaseStatus '{resource['releaseStatus']}' (allowed: {valid})")

    if rtype == "apiResource" and "apiProtocol" in resource:
        valid = enums.get("apiProtocol", [])
        if resource["apiProtocol"] not in valid:
            errors.append(f"INVALID apiProtocol '{resource['apiProtocol']}' (allowed: {valid})")

    if rtype == "entityType" and "level" in resource:
        valid = enums.get("level", [])
        if resource["level"] not in valid:
            errors.append(f"INVALID level '{resource['level']}' (allowed: {valid})")

    if rtype == "dataProduct":
        if "type" in resource:
            valid = enums.get("type_dataProduct", [])
            if resource["type"] not in valid:
                errors.append(f"INVALID type '{resource['type']}' (allowed: {valid})")
        if "category" in resource:
            valid = enums.get("category_dataProduct", [])
            if resource["category"] not in valid:
                errors.append(f"INVALID category '{resource['category']}' (allowed: {valid})")

    return errors


def check_resource_definitions(resource: dict, rtype: str, rules: dict) -> list[str]:
    """Check resourceDefinitions (apiResource/eventResource) and definitions (capability)."""
    errors = []
    if rtype in ("apiResource", "eventResource"):
        required_sub = rules.get(rtype, {}).get("resourceDefinitions_item_required", [])
        for i, rd in enumerate(resource.get("resourceDefinitions", [])):
            for field in required_sub:
                if not rd.get(field):
                    errors.append(f"resourceDefinitions[{i}] MISSING required field '{field}'")
    if rtype == "capability":
        required_sub = rules.get("capability", {}).get("definitions_item_required", [])
        for i, rd in enumerate(resource.get("definitions", [])):
            for field in required_sub:
                if not rd.get(field):
                    errors.append(f"definitions[{i}] MISSING required field '{field}'")
    return errors


def check_aspects(resource: dict, rtype: str, rules: dict) -> list[str]:
    """Check aspects sub-structure for integrationDependency."""
    errors = []
    if rtype != "integrationDependency":
        return []
    aspects = resource.get("aspects", [])
    if not aspects:
        errors.append("MISSING aspects (at least one required)")
        return errors
    required_sub = rules.get("integrationDependency", {}).get("aspects_item_required", [])
    for i, asp in enumerate(aspects):
        for field in required_sub:
            if not asp.get(field):
                errors.append(f"aspects[{i}] MISSING required field '{field}'")
        # Each aspect must have at least one of apiResources, eventResources
        has_resources = bool(asp.get("apiResources") or asp.get("eventResources") or asp.get("dataProducts"))
        if not has_resources:
            errors.append(f"aspects[{i}] has no apiResources, eventResources, or dataProducts")
    return errors


def validate_resource(resource: dict, rtype: str, rules: dict) -> dict:
    """Validate one resource. Returns result dict."""
    ordid = resource.get("ordId", "<no ordId>")
    errors = []
    warnings = []

    errors += check_required_fields(resource, rtype, rules)
    errors += check_ordid_pattern(resource, rtype, rules)
    errors += check_enum_fields(resource, rtype, rules)
    errors += check_resource_definitions(resource, rtype, rules)
    errors += check_aspects(resource, rtype, rules)

    # Semantic field warnings (optional but recommended for ambiguity scoring)
    semantic = rules.get(rtype, {}).get("semantic_fields", [])
    for field in semantic:
        val = resource.get(field)
        if not val or val == [] or val == "":
            warnings.append(f"EMPTY semantic field '{field}' (used in ambiguity scoring)")

    return {
        "ordId": ordid,
        "type": rtype,
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def validate_document(doc: dict, source: str, rules: dict) -> list[dict]:
    """Validate all resources in an ORD document."""
    results = []

    # Check document-level required fields
    doc_required = rules.get("document", {}).get("required", [])
    for field in doc_required:
        if not doc.get(field):
            results.append({
                "ordId": f"<document:{source}>",
                "type": "document",
                "passed": False,
                "errors": [f"MISSING document-level required field '{field}'"],
                "warnings": [],
            })

    # Validate each resource type
    for key, rtype in RESOURCE_KEY_TO_TYPE.items():
        for item in doc.get(key, []):
            results.append(validate_resource(item, rtype, rules))

    return results


def validate_landscape(landscape_dir: Path, rules: dict) -> dict:
    """Validate all ORD documents under a landscape directory."""
    all_results = []
    files_checked = []

    for ns_dir in sorted(landscape_dir.iterdir()):
        if not ns_dir.is_dir():
            continue
        for fname in ["ord.json", "ord_enriched.json"]:
            fpath = ns_dir / fname
            if not fpath.exists():
                continue
            doc = json.loads(fpath.read_text())
            source = f"{ns_dir.name}/{fname}"
            results = validate_document(doc, source, rules)
            for r in results:
                r["source"] = source
            all_results.extend(results)
            files_checked.append(source)

    passed = [r for r in all_results if r["passed"]]
    failed = [r for r in all_results if not r["passed"]]
    warned = [r for r in all_results if r["warnings"]]

    return {
        "files_checked": files_checked,
        "total": len(all_results),
        "passed": len(passed),
        "failed": len(failed),
        "with_warnings": len(warned),
        "results": all_results,
    }


def print_report(report: dict, verbose: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"ORD VALIDATION REPORT")
    print(f"{'='*60}")
    print(f"Files checked : {len(report['files_checked'])}")
    print(f"Total resources: {report['total']}")
    print(f"Passed  : {report['passed']}")
    print(f"Failed  : {report['failed']}")
    print(f"Warnings: {report['with_warnings']}")
    print()

    if report["failed"] > 0:
        print("FAILURES:")
        for r in report["results"]:
            if not r["passed"]:
                print(f"  [{r.get('source','?')}] {r['ordId']} ({r['type']})")
                for e in r["errors"]:
                    print(f"    ✗ {e}")

    if verbose:
        print("\nWARNINGS:")
        for r in report["results"]:
            if r["warnings"]:
                print(f"  [{r.get('source','?')}] {r['ordId']} ({r['type']})")
                for w in r["warnings"]:
                    print(f"    ⚠ {w}")

    status = "PASS" if report["failed"] == 0 else "FAIL"
    print(f"\n{'='*60}")
    print(f"RESULT: {status}")
    print(f"{'='*60}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ORD documents against spec rules")
    parser.add_argument("--landscape", default=str(ROOT / "data" / "landscape" / "systems"),
                        help="Directory containing namespace subdirs with ord.json files")
    parser.add_argument("--file", help="Validate a single ORD document file")
    parser.add_argument("--output", help="Write JSON report to this path")
    parser.add_argument("--verbose", action="store_true", help="Show warnings")
    parser.add_argument("--fail-on-warnings", action="store_true")
    args = parser.parse_args()

    rules = load_rules()

    if args.file:
        doc = json.loads(Path(args.file).read_text())
        results = validate_document(doc, args.file, rules)
        report = {
            "files_checked": [args.file],
            "total": len(results),
            "passed": sum(1 for r in results if r["passed"]),
            "failed": sum(1 for r in results if not r["passed"]),
            "with_warnings": sum(1 for r in results if r["warnings"]),
            "results": results,
        }
    else:
        landscape_dir = Path(args.landscape)
        if not landscape_dir.exists():
            print(f"Landscape directory not found: {landscape_dir}")
            print("Run with --landscape to specify a path, or create data/landscape/systems/ first.")
            return 1
        report = validate_landscape(landscape_dir, rules)

    print_report(report, verbose=args.verbose)

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2))
        print(f"Report written to {args.output}")

    failed = report["failed"] > 0
    warned = args.fail_on_warnings and report["with_warnings"] > 0
    return 1 if (failed or warned) else 0


if __name__ == "__main__":
    sys.exit(main())
