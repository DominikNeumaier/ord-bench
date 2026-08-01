"""Seed landscape generator — Step 1 of Phase 1.

Generates 3 diverse seed resources per system (1 agent, 1 apiResource, 1 dataProduct)
using claude-haiku-4.5. Each resource goes through Judge C1 (validate_ord.py) +
C2-C5 (LLM) before being written to disk.

Usage:
    python benchmark/landscape/generate_seeds.py
    python benchmark/landscape/generate_seeds.py --systems benchmark/landscape/systems
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.core import llm, config
from benchmark.landscape.enrich_landscape import (
    spec_check, save_resource, load_landscape, LOG_PATH
)
from benchmark.landscape.validate_ord import load_rules, validate_resource

SYSTEMS = {
    "sap.s4":      "ERP, Finance, Manufacturing — SAP S/4HANA. Covers financial accounting, procurement, production planning, and asset management.",
    "sap.sf":      "HR and People — SAP SuccessFactors. Covers employee lifecycle, recruiting, performance management, and learning.",
    "sap.ariba":   "Procurement — SAP Ariba. Covers sourcing, purchase orders, invoice management, and vendor onboarding.",
    "sap.crm":     "Sales and Customer — SAP CRM. Covers opportunities, customer accounts, dispute resolution, and sales planning.",
    "sap.ehs":     "Safety and Environment — SAP EHS. Covers incident management, chemical compliance, safety inspections, regulatory reporting, environmental monitoring, waste management, permit management, and emergency response planning.",
    "corp.itsm":   "IT Service Management — Corporate ITSM. Covers service tickets, access provisioning, asset management, and change management.",
    "my.mes":      "Manufacturing Execution — Custom MES. Covers production scheduling, equipment diagnostics, quality inspection, and OEE monitoring.",
    "workday.hcm": "HR (non-SAP) — Workday HCM. Covers compensation, benefits, time-off management, and payroll.",
    "emarsys.cx":  "Marketing and CX — Emarsys. Covers campaign management, customer segmentation, journey orchestration, and engagement analytics.",
    "siemens.plm": "Product Lifecycle — Siemens PLM. Covers bill of materials, engineering changes, design review, digital twin, product configuration, supplier qualification, compliance documentation, and product cost estimation.",
}

ENTITY_TYPES_BY_DOMAIN = {
    "sap.s4":      ["sap.odm:entityType:Material:v1", "sap.odm:entityType:Vendor:v1", "sap.odm:entityType:CustomerOrder:v1", "sap.odm:entityType:Invoice:v1", "sap.odm:entityType:ProductionOrder:v1"],
    "sap.sf":      ["sap.odm:entityType:Employee:v1", "sap.odm:entityType:WorkforcePerson:v1", "sap.odm:entityType:PerformanceReview:v1"],
    "sap.ariba":   ["sap.odm:entityType:Vendor:v1", "sap.odm:entityType:PurchaseOrder:v1", "sap.odm:entityType:Contract:v1"],
    "sap.crm":     ["sap.odm:entityType:CustomerAccount:v1", "sap.odm:entityType:SalesOpportunity:v1", "sap.odm:entityType:CustomerOrder:v1"],
    "sap.ehs":     ["sap.odm:entityType:SafetyIncident:v1", "sap.odm:entityType:HazardousSubstance:v1", "sap.odm:entityType:Incident:v1"],
    "corp.itsm":   ["sap.odm:entityType:ServiceTicket:v1", "sap.odm:entityType:ITEquipment:v1", "sap.odm:entityType:ChangeRequest:v1"],
    "my.mes":      ["sap.odm:entityType:Machine:v1", "sap.odm:entityType:ProductionOrder:v1", "sap.odm:entityType:QualityInspection:v1"],
    "workday.hcm": ["sap.odm:entityType:Employee:v1", "sap.odm:entityType:Compensation:v1", "sap.odm:entityType:TimeOff:v1"],
    "emarsys.cx":  ["sap.odm:entityType:CustomerAccount:v1", "sap.odm:entityType:Campaign:v1", "sap.odm:entityType:CustomerSegment:v1"],
    "siemens.plm": ["sap.odm:entityType:ProductItem:v1", "sap.odm:entityType:EngineeringChange:v1", "sap.odm:entityType:Material:v1"],
}

_SEED_SYS = """You are an ORD (Open Resource Discovery) resource designer for enterprise software benchmarks.
Generate a realistic ORD resource JSON for a given system and resource type.
The resource must be a typical enterprise capability for the system domain.
It must NOT be generic — it should reflect a specific, realistic enterprise use case.

IMPORTANT — shared entity type vocabulary:
The benchmark uses sap.odm as the single cross-system business object vocabulary.
ALL systems (SAP and non-SAP alike — Workday, Siemens, Emarsys, etc.) reference
sap.odm:entityType:* IDs. There is no separate Workday or Siemens entity type namespace.
This is by design: sap.odm IDs are the semantic glue that connects resources across vendors.
Always use sap.odm:entityType:* IDs regardless of which system you are generating for.

Respond with ONLY a valid JSON object, no markdown, no explanation."""

def _seed_prompt(namespace: str, domain: str, rtype: str, entity_types: list[str], existing: list[str]) -> str:
    type_hints = {
        "agent": "An AI agent that performs a specific enterprise task autonomously. Should have clear capabilities and interact with specific business objects.",
        "apiResource": "A REST or OData API that exposes or manages specific business data. Should have clear entity types it operates on.",
        "dataProduct": "An analytical data product providing aggregated metrics or views of business data. type must be 'primary' or 'derived', category must be 'business-object' or 'analytical'.",
    }
    et_str = ", ".join(e.split(":")[-2] for e in entity_types)
    existing_str = "\n".join(f"- {e}" for e in existing) if existing else "none yet"

    return f"""System: {namespace}
Domain: {domain}
Resource type to generate: {rtype}
Hint: {type_hints[rtype]}
Suggested entity types to reference (use 1-3 of these): {et_str}
Already generated for this system (must be different):
{existing_str}

Generate ONE {rtype} resource JSON with these exact fields:
{{
  "ordId": "{namespace}:{rtype}:<PascalCaseName>:v1",
  "title": "<clear title>",
  "shortDescription": "<one sentence, max 120 chars>",
  "description": "<2-3 sentences describing what it does and why it is useful>",
  "version": "1.0.0",
  "lastUpdate": "2026-06-06T00:00:00+00:00",
  "visibility": "public",
  "releaseStatus": "active",
  "partOfPackage": "{namespace}:package:Core:v1",
  {"'type': 'primary'," if rtype == 'dataProduct' else ''}
  {"'category': 'business-object'," if rtype == 'dataProduct' else ''}
  {"'outputPorts': [{{'ordId': '{namespace}:apiResource:Placeholder:v1'}}]," if rtype == 'dataProduct' else ''}
  {"'apiProtocol': 'rest', 'resourceDefinitions': [{{'type': 'openapi-v3', 'mediaType': 'application/json', 'url': '/api/placeholder.json', 'accessStrategies': [{{'type': 'open'}}]}}]," if rtype == 'apiResource' else ''}
  {"'relatedEntityTypes': [<list of sap.odm ordIds>]," if rtype == 'agent' else ''}
  {"'exposedEntityTypes': [{{'ordId': '<sap.odm entityType ordId>'}}]," if rtype in ('apiResource',) else ''}
  {"'entityTypes': ['<sap.odm entityType ordId>']," if rtype == 'dataProduct' else ''}
  "lineOfBusiness": ["<domain name>"],
  "tags": ["<2-4 relevant lowercase tags>"],
  "industry": []
}}

Use only sap.odm entity type IDs from this list: {', '.join(entity_types)}
The ordId PascalCaseName must be descriptive and unique."""


_JUDGE_SYS = """You are a benchmark quality judge for ORD resources in an enterprise software landscape.
Evaluate whether a generated resource meets criteria C2-C5.
C1 (spec compliance) has already passed — do not re-evaluate it.

IMPORTANT — shared entity type vocabulary:
The benchmark uses sap.odm as the single cross-system business object vocabulary.
ALL systems — including non-SAP systems like Workday HCM, Siemens PLM, Emarsys CX — reference
sap.odm:entityType:* IDs. This is intentional: sap.odm IDs are the semantic glue connecting
resources across vendors. NEVER reject a resource for using sap.odm entity types, regardless
of the system namespace. A Workday resource referencing sap.odm:entityType:Employee:v1 is correct.

Respond with ONLY a JSON object."""

def _judge_prompt(resource: dict, namespace: str, domain: str, existing: list[str]) -> str:
    existing_str = "\n".join(f"- {e}" for e in existing) if existing else "none"
    return f"""Evaluate this ORD resource for the {namespace} system ({domain}).

Resource:
{json.dumps(resource, indent=2)}

Already existing resources in this system:
{existing_str}

Evaluate C2-C5 and respond with:
{{
  "c2_coherent": true/false,
  "c2_reason": "one sentence — is this a plausible resource for {namespace}?",
  "c3_not_duplicate": true/false,
  "c3_reason": "one sentence — is it sufficiently different from existing resources?",
  "c4_et_justified": true/false,
  "c4_reason": "one sentence — are the entity type references semantically appropriate for this resource's domain?",
  "c5_na": true,
  "accepted": true/false,
  "reject_reason": "if not accepted: one sentence explaining why"
}}"""


def generate_package(namespace: str, systems_dir: Path) -> None:
    """Ensure the package entry exists for this namespace."""
    ns_dir = systems_dir / namespace
    ns_dir.mkdir(parents=True, exist_ok=True)
    ord_path = ns_dir / "ord.json"

    if ord_path.exists():
        doc = json.loads(ord_path.read_text())
        if doc.get("packages"):
            return  # already has package
    else:
        doc = {
            "openResourceDiscovery": "1.16",
            "perspective": "system-instance",
            "packages": [],
            "agents": [],
            "apiResources": [],
            "dataProducts": [],
        }

    pkg_ordid = f"{namespace}:package:Core:v1"
    doc["packages"] = [{
        "ordId": pkg_ordid,
        "title": f"{namespace} Core Package",
        "shortDescription": f"Core resources for the {namespace} system in the benchmark landscape.",
        "version": "1.0.0",
        "vendor": "sap:vendor:SAP:" if namespace.startswith("sap") else f"{namespace.split('.')[0]}:vendor:Default:",
    }]
    ord_path.write_text(json.dumps(doc, indent=2))
    print(f"  Created package {pkg_ordid}")


def generate_one_seed(namespace: str, domain: str, rtype: str,
                      entity_types: list[str], existing_ordids: list[str],
                      systems_dir: Path, max_attempts: int = 5) -> dict | None:
    """Generate one seed resource via LLM + Judge. Returns accepted resource or None."""
    rules = load_rules()

    for attempt in range(1, max_attempts + 1):
        # Generator
        prompt = _seed_prompt(namespace, domain, rtype, entity_types, existing_ordids)
        text, meta = llm.chat(prompt, system=_SEED_SYS)

        # Parse JSON
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            print(f"    attempt {attempt}: Generator returned no JSON")
            continue
        try:
            resource = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            print(f"    attempt {attempt}: JSON parse error — {e}")
            continue

        resource["_rtype"] = rtype
        resource["namespace"] = namespace

        # C1: spec check (deterministic)
        passed, spec_errors = spec_check(resource)
        if not passed:
            print(f"    attempt {attempt}: C1 FAIL — {spec_errors[:3]}")
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase": "seed",
                "action": "create",
                "outcome": "rejected_c1",
                "namespace": namespace,
                "rtype": rtype,
                "attempt": attempt,
                "spec_errors": spec_errors,
            }
            _append_log(log_entry)
            continue

        # C2-C5: Judge (LLM)
        judge_prompt = _judge_prompt(resource, namespace, domain, existing_ordids)
        judge_text, judge_meta = llm.chat(judge_prompt, system=_JUDGE_SYS)
        jm = re.search(r"\{[\s\S]*\}", judge_text)
        if not jm:
            print(f"    attempt {attempt}: Judge returned no JSON")
            continue
        try:
            verdict = json.loads(jm.group(0))
        except json.JSONDecodeError:
            print(f"    attempt {attempt}: Judge JSON parse error")
            continue

        accepted = verdict.get("accepted", False)
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "seed",
            "action": "create",
            "outcome": "accepted" if accepted else "rejected_judge",
            "namespace": namespace,
            "rtype": rtype,
            "ordId": resource.get("ordId"),
            "attempt": attempt,
            "generator_tokens": meta.get("tokens", 0),
            "judge_tokens": judge_meta.get("tokens", 0),
            "judge_verdict": verdict,
        }
        _append_log(log_entry)

        if accepted:
            print(f"    attempt {attempt}: ACCEPTED — {resource.get('ordId')}")
            save_resource(resource, systems_dir)
            return resource
        else:
            reason = verdict.get("reject_reason", "no reason given")
            print(f"    attempt {attempt}: Judge rejected — {reason}")

    return None


def _append_log(entry: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries = json.loads(LOG_PATH.read_text()) if LOG_PATH.exists() else []
    entries.append(entry)
    LOG_PATH.write_text(json.dumps(entries, indent=2))


def _already_saved(namespace: str, rtype: str, systems_dir: Path) -> list[str]:
    """Return ordIds of resources of rtype already saved for namespace."""
    ord_path = systems_dir / namespace / "ord.json"
    if not ord_path.exists():
        return []
    doc = json.loads(ord_path.read_text())
    key_map = {"agent": "agents", "apiResource": "apiResources", "dataProduct": "dataProducts"}
    return [r.get("ordId", "") for r in doc.get(key_map.get(rtype, ""), [])]


def run_seed_generation(systems_dir: Path) -> None:
    print(f"\nGenerating seed resources into {systems_dir}")
    print(f"Model: {config.LLM_MODEL}\n")

    total_accepted = 0
    total_attempted = 0

    for namespace, domain in SYSTEMS.items():
        print(f"\n{'='*60}")
        print(f"System: {namespace}")
        print(f"Domain: {domain[:60]}")

        # Ensure package exists
        generate_package(namespace, systems_dir)

        entity_types = ENTITY_TYPES_BY_DOMAIN.get(namespace, [])
        existing_ordids: list[str] = []

        for rtype in ["agent", "apiResource", "dataProduct"]:
            # Skip if already saved from a previous run
            saved = _already_saved(namespace, rtype, systems_dir)
            if saved:
                print(f"\n  → {rtype}: already saved ({saved[0]}) — skipping")
                existing_ordids.extend(saved)
                total_accepted += 1
                total_attempted += 1
                continue

            print(f"\n  → Generating {rtype}...")
            total_attempted += 1

            result = generate_one_seed(
                namespace=namespace,
                domain=domain,
                rtype=rtype,
                entity_types=entity_types,
                existing_ordids=existing_ordids,
                systems_dir=systems_dir,
            )

            if result:
                existing_ordids.append(result.get("ordId", ""))
                total_accepted += 1
            else:
                print(f"  ✗ Could not generate {rtype} for {namespace} after 5 attempts")

    print(f"\n{'='*60}")
    print(f"SEED GENERATION COMPLETE")
    print(f"Accepted: {total_accepted}/{total_attempted}")
    print(f"Log: {LOG_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate seed resources for benchmark landscape")
    parser.add_argument(
        "--systems",
        default=str(ROOT / "benchmark" / "landscape" / "systems"),
    )
    args = parser.parse_args()

    systems_dir = Path(args.systems)
    run_seed_generation(systems_dir)


if __name__ == "__main__":
    main()
