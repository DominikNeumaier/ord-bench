"""Adversarial landscape enrichment game.

Three-party game: Generator → Solver (deterministic) → Judge
Runs until every ground-truth resource has:
  - >= MIN_HIGH  neighbors with sim >= HIGH_THRESHOLD
  - >= MIN_MEDIUM neighbors with sim >= MEDIUM_THRESHOLD
  - >= MIN_LOW   neighbors with sim >= LOW_THRESHOLD

Usage:
    python src/generation/enrich_landscape.py
    python src/generation/enrich_landscape.py --systems data/landscape/systems --max-attempts 5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# Uses claude-haiku-4.5 by default (config.LLM_MODEL) to keep costs low.
# The enrichment loop can make hundreds of Generator + Judge calls.
# Override with: LLM_MODEL=anthropic--claude-opus-4-5 python src/generation/enrich_landscape.py

from src.adversarial.preselect import (
    compute_landscape_ambiguity,
    _pairwise_sim,
    _et_idf,
    _build_tfidf_index,
    GROUND_TRUTH_TYPES,
)

# ── Tier thresholds (fixed before any run) ───────────────────────────────────

HIGH_THRESHOLD   = 0.50
MEDIUM_THRESHOLD = 0.25
LOW_THRESHOLD    = 0.10
LOW_MAX          = MEDIUM_THRESHOLD  # low must be < medium threshold

MIN_HIGH   = 3
MIN_MEDIUM = 5
MIN_LOW    = 5

MAX_ATTEMPTS_PER_FILL = 5   # Generator retries before giving up on a tier-fill
MIN_SYSTEM_SPREAD     = 3   # neighbors must come from at least this many different systems per tier

LOG_PATH    = ROOT / "data" / "landscape" / "logs" / "enrichment_log.json"
REPORT_PATH = ROOT / "data" / "landscape" / "logs" / "enrichment_report.md"


# ── Load / save landscape ────────────────────────────────────────────────────


def load_landscape(systems_dir: Path) -> list[dict]:
    """Load all resources from ord.json files under systems_dir."""
    resources = []
    for ns_dir in sorted(systems_dir.iterdir()):
        if not ns_dir.is_dir():
            continue
        for fname in ["ord.json", "ord_enriched.json"]:
            p = ns_dir / fname
            if not p.exists():
                continue
            doc = json.loads(p.read_text())
            for key, rtype in [
                ("agents", "agent"),
                ("apiResources", "apiResource"),
                ("dataProducts", "dataProduct"),
                ("eventResources", "eventResource"),
            ]:
                for r in doc.get(key, []):
                    r["_rtype"] = rtype
                    r["namespace"] = ns_dir.name
                    resources.append(r)
            break  # prefer ord.json; skip ord_enriched.json if ord.json exists
    return resources


def save_resource(resource: dict, systems_dir: Path) -> None:
    """Append a new resource to the appropriate system's ord.json."""
    ns = resource.get("namespace", "")
    ns_dir = systems_dir / ns
    ns_dir.mkdir(parents=True, exist_ok=True)
    ord_path = ns_dir / "ord.json"

    if ord_path.exists():
        doc = json.loads(ord_path.read_text())
    else:
        doc = {
            "openResourceDiscovery": "1.16",
            "description": f"ORD document for {ns}",
            "packages": [],
        }

    type_to_key = {
        "agent": "agents",
        "apiResource": "apiResources",
        "dataProduct": "dataProducts",
        "eventResource": "eventResources",
    }
    key = type_to_key.get(resource.get("_rtype", ""), "apiResources")
    arr = doc.setdefault(key, [])

    # Remove internal fields before saving
    r_clean = {k: v for k, v in resource.items() if k not in ("_rtype", "namespace")}
    arr.append(r_clean)

    ord_path.write_text(json.dumps(doc, indent=2))


def _replace_resource_on_disk(resource: dict, systems_dir: Path) -> None:
    """Replace an existing resource in ord.json with the modified version."""
    ns = resource.get("namespace", "")
    old_ordid = resource.get("_modifies", "")
    if not old_ordid or not ns:
        save_resource(resource, systems_dir)
        return

    ord_path = systems_dir / ns / "ord.json"
    if not ord_path.exists():
        save_resource(resource, systems_dir)
        return

    doc = json.loads(ord_path.read_text())
    type_to_key = {
        "agent": "agents", "apiResource": "apiResources",
        "dataProduct": "dataProducts", "eventResource": "eventResources",
    }
    r_clean = {k: v for k, v in resource.items()
               if not k.startswith("_") and k != "namespace"}

    replaced = False
    for key in type_to_key.values():
        arr = doc.get(key, [])
        for i, r in enumerate(arr):
            if r.get("ordId") == old_ordid:
                arr[i] = r_clean
                replaced = True
                break
        if replaced:
            break

    if not replaced:
        # Old resource not found in this namespace — just append as new
        rtype = resource.get("_rtype", "apiResource")
        doc.setdefault(type_to_key.get(rtype, "apiResources"), []).append(r_clean)

    ord_path.write_text(json.dumps(doc, indent=2))


# ── Tier analysis ─────────────────────────────────────────────────────────────


def tier_status(resource_entry: dict) -> dict:
    """Return current tier counts and which tiers still need filling."""
    neighbors = resource_entry.get("all_neighbors", [])

    high   = [nb for nb in neighbors if nb["sim"] >= HIGH_THRESHOLD]
    medium = [nb for nb in neighbors if MEDIUM_THRESHOLD <= nb["sim"] < HIGH_THRESHOLD]
    low    = [nb for nb in neighbors if LOW_THRESHOLD <= nb["sim"] < MEDIUM_THRESHOLD]

    # System spread per tier
    def spread(nbs: list[dict]) -> int:
        return len(set(nb.get("namespace", nb["ordId"].split(":")[0]) for nb in nbs))

    return {
        "high":          {"count": len(high),   "needed": max(0, MIN_HIGH   - len(high)),   "spread": spread(high)},
        "medium":        {"count": len(medium), "needed": max(0, MIN_MEDIUM - len(medium)), "spread": spread(medium)},
        "low":           {"count": len(low),    "needed": max(0, MIN_LOW    - len(low)),    "spread": spread(low)},
        "done":          len(high) >= MIN_HIGH and len(medium) >= MIN_MEDIUM and len(low) >= MIN_LOW,
    }


def all_done(report: dict) -> bool:
    """Return True when every ground-truth resource has met all tier targets."""
    for r in report["resources"]:
        if not r["can_be_ground_truth"]:
            continue
        status = tier_status(r)
        if not status["done"]:
            return False
    return True


# ── Spec validation (calls validate_ord.py deterministically) ────────────────


def spec_check(resource: dict) -> tuple[bool, list[str]]:
    """Run validate_ord.py on a single resource. Returns (passed, errors)."""
    import subprocess
    validate_script = ROOT / "src" / "generation" / "validate_ord.py"
    # Write resource to a temp file
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp_path = tmp.name
    type_to_key = {
        "agent": "agents", "apiResource": "apiResources",
        "dataProduct": "dataProducts", "eventResource": "eventResources",
    }
    key = type_to_key.get(resource.get("_rtype", ""), "apiResources")
    r_clean = {k: v for k, v in resource.items() if k not in ("_rtype", "namespace")}
    doc = {"openResourceDiscovery": "1.16", key: [r_clean]}
    tmp.write(json.dumps(doc))
    tmp.close()

    try:
        result = subprocess.run(
            [sys.executable, str(validate_script), "--file", tmp_path],
            capture_output=True, text=True
        )
        passed = "RESULT: PASS" in result.stdout
        errors = [
            line.strip().lstrip("✗ ")
            for line in result.stdout.splitlines()
            if "✗" in line
        ]
        return passed, errors
    finally:
        os.unlink(tmp_path)


import re
from src import llm

MAX_LANDSCAPE_SIZE = 200  # hard cap — Generator must prefer modify once reached

SYSTEMS_DOMAINS = {
    "sap.s4":      "ERP, Finance, Manufacturing — SAP S/4HANA",
    "sap.sf":      "HR and People — SAP SuccessFactors",
    "sap.ariba":   "Procurement — SAP Ariba",
    "sap.crm":     "Sales and Customer — SAP CRM",
    "sap.ehs":     "Safety and Environment — SAP EHS",
    "corp.itsm":   "IT Service Management — Corporate ITSM",
    "my.mes":      "Manufacturing Execution — Custom MES",
    "workday.hcm": "HR (non-SAP) — Workday HCM",
    "emarsys.cx":  "Marketing and CX — Emarsys",
    "siemens.plm": "Product Lifecycle — Siemens PLM. Covers bill of materials, engineering changes, design review, digital twin, product configuration, supplier qualification, compliance documentation, and product cost estimation.",
}

_GEN_SYS = """You are an ORD (Open Resource Discovery) landscape architect for an enterprise benchmark.
Your job is to fill similarity tiers in the landscape by either creating a new resource or modifying an existing one.

The benchmark uses sap.odm as the single cross-system entity type vocabulary for ALL systems — including
non-SAP systems like Workday, Siemens, and Emarsys. Always use sap.odm:entityType:* IDs.

The similarity metric has 6 equal-weight dimensions:
  1. text (TF-IDF cosine on title+shortDescription+description)
  2. localId (Jaccard on CamelCase tokens of the ordId name segment)
  3. entityTypes (IDF-weighted Jaccard on relatedEntityTypes/exposedEntityTypes/entityTypes)
  4. lineOfBusiness (Jaccard)
  5. tags (Jaccard)
  6. industry (Jaccard)
Plus: +0.5 cross-namespace bonus (before /6), ×0.5 type-penalty if different resource type.

To hit HIGH (≥0.50): maximize shared entityTypes + same lineOfBusiness + cross-namespace bonus
To hit MEDIUM (0.25–0.50): partial entityType overlap OR same type with different LoB
To hit LOW (0.10–0.25): 1-2 shared entityTypes, different type (type penalty helps), minimal text overlap

Respond with ONLY a valid JSON object."""

_ENRICHMENT_MODEL = "anthropic--claude-4.5-haiku"

_JUDGE_SYS = """You are a benchmark quality judge for ORD resources in the ENRICHMENT phase.
C1 (spec compliance) has already passed. Evaluate C2–C5.

IMPORTANT CONTEXT — this is a synthetic benchmark, not production ORD:
The explicit goal of the enrichment phase is to create structural ambiguity by making resources
more similar to each other. This means a resource may be rewritten to reference entity types or
lineOfBusiness values from a neighbouring domain — this is intentional and correct for the benchmark.

Accept modifications that:
- Keep the resource recognizable as a plausible enterprise resource for its system
- Use sap.odm entity types that are at least somewhat related to the system domain
- Do NOT completely abandon the system's core domain (e.g. an HR system should still have HR context)

Reject only if:
- The resource makes no sense at all for the system (e.g. a weather forecast in a procurement system)
- The entity types are completely unrelated to BOTH the system domain AND the target domain
- The resource is an exact duplicate of an existing resource

The benchmark uses sap.odm as the single cross-system entity type vocabulary for ALL systems.
Never reject for using sap.odm entity types from a neighbouring domain.

Respond with ONLY a JSON object."""


def _tier_hint(tier: str) -> str:
    hints = {
        "high":   "sim ≥ 0.50 — same entityTypes + same lineOfBusiness, ideally cross-namespace",
        "medium": "0.25 ≤ sim < 0.50 — partial entityType overlap OR same type/different LoB",
        "low":    "0.10 ≤ sim < 0.25 — 1-2 shared entityTypes, different resource type preferred",
    }
    return hints.get(tier, "")


def _format_breakdown(breakdown: dict) -> str:
    parts = []
    for k in ("text", "localId", "entityTypes", "lineOfBusiness", "tags", "industry"):
        v = breakdown.get(k)
        if v is not None:
            parts.append(f"{k}={v:.3f}")
    if breakdown.get("cross_namespace_bonus_applied"):
        parts.append("cross-ns=+0.5")
    if breakdown.get("type_penalty_applied"):
        parts.append("type-penalty=×0.5")
    return ", ".join(parts)



def generator_act(
    target: dict,
    tier: str,
    landscape: list[dict],
    attempt: int,
    existing_neighbor_ids: list[str],
    prev_breakdown: dict | None,
    systems_dir: Path,
    candidate_ordid: str | None = None,
) -> dict | None:
    """Generator: rewrite an existing resource so sim(target, rewritten) lands in tier.

    Selects the best candidate automatically (highest current sim not yet in tier),
    or uses candidate_ordid if provided.

    Returns modified resource dict with internal keys:
      _rtype, namespace, _action="modify", _modifies, _decision_reason, _field_strategy
    Returns None on parse failure.
    """
    # Select candidate: highest sim to target not already in target tier
    idf = _et_idf(landscape)
    tfidf = _build_tfidf_index(landscape)

    tier_lo = {"high": HIGH_THRESHOLD, "medium": MEDIUM_THRESHOLD, "low": LOW_THRESHOLD}
    tier_hi = {"high": 999, "medium": HIGH_THRESHOLD, "low": MEDIUM_THRESHOLD}
    lo, hi = tier_lo[tier], tier_hi[tier]

    in_tier_ids = set(existing_neighbor_ids)  # already satisfy this tier

    if candidate_ordid:
        candidates = [r for r in landscape if r.get("ordId") == candidate_ordid]
    else:
        scored = []
        for r in landscape:
            oid = r.get("ordId", "")
            if oid == target.get("ordId") or oid in in_tier_ids:
                continue
            if r.get("_rtype") not in ("agent", "apiResource", "dataProduct"):
                continue
            sim, bd = _pairwise_sim(target, r, idf, tfidf)
            # Prefer candidates just below threshold (high proximity → small modification needed)
            scored.append((sim, r, bd))
        scored.sort(key=lambda x: -x[0])
        # On repeated attempts, try progressively lower-ranked candidates
        idx = min(attempt - 1, len(scored) - 1)
        candidates = [scored[idx][1]] if scored else []

    if not candidates:
        return None

    cand = candidates[0]
    cand_sim, cand_bd = _pairwise_sim(target, cand, idf, tfidf)

    target_ets = _extract_entity_types_str(target)   # display string for prompt
    cand_ets   = _extract_entity_types_str(cand)
    ns_cand    = cand.get("namespace", "?")
    domain     = SYSTEMS_DOMAINS.get(ns_cand, ns_cand)

    # Full ordId set — used for deterministic ET enforcement after LLM call
    target_et_ids: set[str] = set()
    for et in (target.get("relatedEntityTypes") or []):
        target_et_ids.add(et if isinstance(et, str) else et.get("ordId", ""))
    for et in (target.get("exposedEntityTypes") or []):
        target_et_ids.add(et if isinstance(et, str) else et.get("ordId", ""))
    for et in (target.get("entityTypes") or []):
        target_et_ids.add(et if isinstance(et, str) else et.get("ordId", ""))
    target_et_ids.discard("")

    breakdown_info = _format_breakdown(cand_bd)
    prev_info = f"\nPrevious attempt breakdown: {_format_breakdown(prev_breakdown)}" if prev_breakdown else ""

    # Compute what each field change would contribute
    tier_threshold = {"high": HIGH_THRESHOLD, "medium": MEDIUM_THRESHOLD, "low": LOW_THRESHOLD}[tier]
    lob_gain  = (1.0 - cand_bd.get("lineOfBusiness", 0.0)) / 6
    tags_gain = (1.0 - cand_bd.get("tags", 0.0)) / 6
    et_gain   = (1.0 - cand_bd.get("entityTypes", 0.0)) / 6
    gap = tier_threshold - cand_sim

    # Build explicit action plan based on breakdown
    action_plan = []
    if cand_bd.get("entityTypes", 0) < 0.8:
        et_list = ", ".join(f'"{e}"' for e in sorted(target_ets))
        rtype_field = {"agent": "relatedEntityTypes", "apiResource": "exposedEntityTypes (as [{ordId:...}])", "dataProduct": "entityTypes"}.get(cand.get("_rtype",""), "entityTypes")
        action_plan.append(f"REQUIRED: Set {rtype_field} to match target: [{et_list}] — this adds +{et_gain:.3f} to score")
    if cand_bd.get("lineOfBusiness", 0) < 1.0:
        lob_val = ", ".join(f'"{v}"' for v in sorted(target.get("lineOfBusiness") or []))
        action_plan.append(f"REQUIRED: Set lineOfBusiness to [{lob_val}] — this adds +{lob_gain:.3f} to score")
    if cand_bd.get("tags", 0) < 0.5:
        shared_tags = sorted(set(target.get("tags") or []))
        action_plan.append(f"HELPFUL: Add shared tags {shared_tags} — this adds ~+{tags_gain:.3f} to score")
    if gap > sum([et_gain, lob_gain]):
        action_plan.append("REQUIRED: Also align title/description/shortDescription content to match target domain vocabulary")

    tier_threshold = {"high": HIGH_THRESHOLD, "medium": MEDIUM_THRESHOLD, "low": LOW_THRESHOLD}[tier]

    prompt = f"""You are rewriting an ORD resource to increase its similarity to a target resource.
The similarity metric has 6 equal-weight dimensions: text, localId, entityTypes, lineOfBusiness, tags, industry.
Plus: cross-namespace +0.5 bonus, type-mismatch ×0.5 penalty.
Formula: (text + localId + entityTypes + lineOfBusiness + tags + industry + 0.5_if_cross_ns) / 6

TARGET resource (do NOT modify this):
  ordId:           {target.get('ordId')}
  type:            {target.get('_rtype', '?')}
  namespace:       {target.get('namespace', '?')}
  title:           {target.get('title', '')}
  shortDescription:{target.get('shortDescription', '')}
  entityTypes:     {sorted(target_ets)}
  lineOfBusiness:  {sorted(target.get('lineOfBusiness') or [])}
  tags:            {sorted(target.get('tags') or [])}

CANDIDATE to rewrite:
  ordId:           {cand.get('ordId')}
  type:            {cand.get('_rtype', '?')}
  namespace:       {ns_cand} ({domain})
  title:           {cand.get('title', '')}
  entityTypes:     {cand_ets}
  lineOfBusiness:  {', '.join(cand.get('lineOfBusiness') or [])}
  tags:            {', '.join(cand.get('tags') or [])}

Current similarity: {cand_sim:.3f}  |  Need: >= {tier_threshold:.2f}  |  Gap: {gap:+.3f}
Score breakdown: {breakdown_info}
{prev_info}
REQUIRED ACTIONS to close the gap (do ALL of these):
{chr(10).join('  ' + a for a in action_plan) if action_plan else '  - Align content vocabulary to target domain'}

FIELDS YOU MUST SET in the rewritten candidate:
  - entityTypes: MUST match target's entity types (this is the single most important field)
  - lineOfBusiness: MUST match target's lineOfBusiness exactly
  - title/description: rewrite to reflect the new entity types and domain focus
  - tags: include target's tags plus any relevant additional tags

FIELDS YOU MUST PRESERVE (do not change these):
  ordId, partOfPackage, visibility, releaseStatus, version, apiProtocol,
  resourceDefinitions (for apiResource), outputPorts + type + category (for dataProduct)

The rewritten resource must be a plausible enterprise resource for {ns_cand} ({domain}).
A full content rewrite is acceptable and expected — the goal is to create a resource that is
genuinely similar to the target while still fitting the {ns_cand} system domain.

Respond with ONLY a JSON object containing the COMPLETE rewritten resource plus:
  "_decision_reason": "one sentence — what you changed and why",
  "_field_strategy": "which specific fields you changed to close the gap"
"""

    text, meta = llm.chat(prompt, system=_GEN_SYS, model=_ENRICHMENT_MODEL)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None

    # Enforce structural fields from original candidate
    for field in ("ordId", "partOfPackage", "visibility", "releaseStatus", "version"):
        if cand.get(field):
            data[field] = cand[field]
    if cand.get("_rtype") == "apiResource":
        for field in ("apiProtocol", "resourceDefinitions"):
            if cand.get(field):
                data[field] = cand[field]
    if cand.get("_rtype") == "dataProduct":
        for field in ("outputPorts", "type", "category"):
            if cand.get(field):
                data[field] = cand[field]

    # Enforce ET + LoB alignment when targeting HIGH or MEDIUM tier.
    # The LLM sometimes fails to set these critical fields despite explicit instructions.
    # We override deterministically because the Judge will verify semantic coherence (C4/C5).
    rtype = cand.get("_rtype", "")
    if tier == "high" and target_et_ids:
        # For HIGH: force full ET alignment — biggest single lever
        if rtype == "agent":
            data["relatedEntityTypes"] = sorted(target_et_ids)
        elif rtype == "apiResource":
            data["exposedEntityTypes"] = [{"ordId": e} for e in sorted(target_et_ids)]
        elif rtype == "dataProduct":
            data["entityTypes"] = sorted(target_et_ids)
        data["lineOfBusiness"] = list(target.get("lineOfBusiness", []))

    data["_rtype"]            = cand.get("_rtype", "apiResource")
    data["namespace"]         = ns_cand
    data["_action"]           = "modify"
    data["_modifies"]         = cand.get("ordId")
    data["_decision_reason"]  = data.get("_decision_reason", "")
    data["_field_strategy"]   = data.get("_field_strategy", "")
    data["_generator_tokens"] = meta.get("tokens", 0)

    return data


def _extract_entity_types_str(r: dict) -> str:
    ets = []
    for et in r.get("relatedEntityTypes") or []:
        ets.append(et if isinstance(et, str) else et.get("ordId", ""))
    for et in r.get("exposedEntityTypes") or []:
        ets.append(et if isinstance(et, str) else et.get("ordId", ""))
    for et in r.get("entityTypes") or []:
        ets.append(et if isinstance(et, str) else et.get("ordId", ""))
    names = [e.split(":")[2] if e.count(":") >= 2 else e for e in ets if e]
    return ", ".join(names) or "(none)"


def judge_evaluate(
    resource: dict,
    target: dict,
    tier: str,
    achieved_sim: float,
    breakdown: dict,
    action: str,
) -> tuple[bool, str]:
    """Judge: C2-C5 evaluation after C1 (spec_check) has passed.

    Returns (accepted, reason).
    """
    namespace = resource.get("namespace", "?")
    domain = SYSTEMS_DOMAINS.get(namespace, namespace)
    action_note = ""
    if action == "modify":
        action_note = f"\nThis is a MODIFICATION of an existing resource (original ordId: {resource.get('_modifies', '?')}). Evaluate whether the modified resource still makes sense for its system domain (C5)."

    prompt = f"""A Generator produced this ORD resource to fill the {tier.upper()} tier
(target sim {'>=' if tier=='high' else '0.25–0.50' if tier=='medium' else '0.10–0.25'}) for:
  target: {target.get('ordId')}
  achieved similarity: {achieved_sim:.3f}
  score breakdown: {_format_breakdown(breakdown)}
  generator action: {action}
  generator decision: {resource.get('_decision_reason', '')}
  field strategy: {resource.get('_field_strategy', '')}
{action_note}

System: {namespace} ({domain})

Resource:
{json.dumps({k: v for k, v in resource.items() if not k.startswith("_")}, indent=2)}

Evaluate C2–C5:
{{
  "c2_coherent": true/false,
  "c2_reason": "is this a plausible resource for {namespace}?",
  "c3_not_duplicate": true/false,
  "c3_reason": "is it sufficiently different from existing resources in its system?",
  "c4_et_justified": true/false,
  "c4_reason": "are entityType references semantically appropriate, not just added to game the score?",
  "c5_modify_ok": true/false,
  "c5_reason": "if modify: does modified resource still make domain sense? If create: true",
  "accepted": true/false,
  "reject_reason": "if not accepted: one sentence explaining the primary failure"
}}"""

    text, meta = llm.chat(prompt, system=_JUDGE_SYS, model=_ENRICHMENT_MODEL)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return False, "Judge returned no JSON"
    try:
        verdict = json.loads(m.group(0))
    except json.JSONDecodeError:
        return False, "Judge JSON parse error"

    accepted = verdict.get("accepted", False)
    reason = verdict.get("reject_reason", "") if not accepted else "accepted"
    return accepted, reason, verdict, meta.get("tokens", 0)


# ── Logging ───────────────────────────────────────────────────────────────────


def log_action(entry: dict, log_path: Path) -> None:
    """Append one enrichment action to the log file (append-safe)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Use append mode with a JSON-lines-style approach to avoid full-file rewrite race conditions.
    # On first write, create a valid JSON array. On subsequent writes, patch in the new entry.
    line = json.dumps(entry)
    if not log_path.exists():
        log_path.write_text(f"[\n{line}\n]")
        return
    # Atomic-enough: read, parse with recovery, append, write
    text = log_path.read_text()
    try:
        decoder = json.JSONDecoder()
        entries, _ = decoder.raw_decode(text)
    except json.JSONDecodeError:
        entries = []
    entries.append(entry)
    log_path.write_text(json.dumps(entries, indent=2))


def print_progress(report: dict, systems_dir: Path) -> None:
    """Print live status: total resources, per-tier completion."""
    resources = load_landscape(systems_dir)
    n_total = len(resources)
    n_by_type: dict[str, int] = {}
    for r in resources:
        n_by_type[r.get("_rtype", "?")] = n_by_type.get(r.get("_rtype", "?"), 0) + 1

    gt_resources = [r for r in report["resources"] if r["can_be_ground_truth"]]
    n_done = sum(1 for r in gt_resources if tier_status(r)["done"])
    n_total_gt = len(gt_resources)

    ts = tier_status
    n_high_done   = sum(1 for r in gt_resources if ts(r)["high"]["needed"] == 0)
    n_medium_done = sum(1 for r in gt_resources if ts(r)["medium"]["needed"] == 0)
    n_low_done    = sum(1 for r in gt_resources if ts(r)["low"]["needed"] == 0)

    print(
        f"\r  Resources: {n_total:3d} total "
        f"(API={n_by_type.get('apiResource',0)} "
        f"Agent={n_by_type.get('agent',0)} "
        f"DP={n_by_type.get('dataProduct',0)})  |  "
        f"Tier complete: high={n_high_done}/{n_total_gt}  "
        f"medium={n_medium_done}/{n_total_gt}  "
        f"low={n_low_done}/{n_total_gt}  "
        f"[{n_done}/{n_total_gt} fully done]",
        end="", flush=True
    )


# ── Main game loop ────────────────────────────────────────────────────────────


def run_enrichment(systems_dir: Path, max_attempts: int = MAX_ATTEMPTS_PER_FILL) -> None:
    print(f"Loading landscape from {systems_dir}...")
    resources = load_landscape(systems_dir)
    print(f"  {len(resources)} resources loaded\n")

    # Track (ordId, tier) pairs that have been exhausted — skip on next outer loop pass
    skipped: set[tuple[str, str]] = set()

    # Track (target_ordId, candidate_ordId) pairs already modified — avoid re-modifying
    # the same candidate for the same target (causes HIGH↔MEDIUM oscillation)
    modified_pairs: set[tuple[str, str]] = set()

    while True:
        report = compute_landscape_ambiguity(resources, top_k=25)
        print_progress(report, systems_dir)

        if all_done(report):
            print("\n\nAll tier targets met. Enrichment complete.")
            break

        # Find the next resource+tier that still needs work and hasn't been skipped
        target_entry = None
        target_tier = None
        for r in report["resources"]:
            if not r["can_be_ground_truth"]:
                continue
            status = tier_status(r)
            if status["done"]:
                continue
            for tier in ("high", "medium", "low"):
                if status[tier]["needed"] > 0 and (r["ordId"], tier) not in skipped:
                    target_entry = r
                    target_tier = tier
                    break
            if target_entry:
                break

        if not target_entry:
            # All remaining gaps are in skipped set — nothing more can be done
            print(f"\n\nNo more fillable gaps. Enrichment stopping.")
            print(f"Skipped tier-fills: {len(skipped)}")
            break

        by_id = {r["ordId"]: r for r in resources}
        target_resource = by_id[target_entry["ordId"]]
        status = tier_status(target_entry)
        print(f"\n  → [{target_tier}] {target_entry['ordId']}"
              f"  (have {status[target_tier]['count']}/{MIN_HIGH if target_tier=='high' else MIN_MEDIUM if target_tier=='medium' else MIN_LOW})")

        idf   = _et_idf(resources)
        tfidf = _build_tfidf_index(resources)

        success = False
        prev_breakdown: dict | None = None
        existing_neighbor_ids = [
            nb["ordId"] for nb in target_entry.get("all_neighbors", [])
            if _tier_of(nb["sim"]) == target_tier
        ]

        # Try multiple candidates: for each candidate, up to 3 attempts
        # If all candidates exhausted without success → tier_skip
        tried_candidates: set[str] = set()
        attempt = 0

        for cand_idx in range(max_attempts):
            # Pick the cand_idx-th best candidate not yet tried.
            # Score candidates by POTENTIAL sim after modification:
            #   simulate aligning ET + LoB to target → upper-bound score estimate.
            # This ensures we pick candidates that CAN reach the tier, not just
            # those already closest in raw score.
            idf2   = _et_idf(resources)
            tfidf2 = _build_tfidf_index(resources)

            target_ets = set()
            for et in (target_resource.get("relatedEntityTypes") or []):
                target_ets.add(et if isinstance(et, str) else et.get("ordId", ""))
            for et in (target_resource.get("exposedEntityTypes") or []):
                target_ets.add(et if isinstance(et, str) else et.get("ordId", ""))
            for et in (target_resource.get("entityTypes") or []):
                target_ets.add(et if isinstance(et, str) else et.get("ordId", ""))
            target_lob = set(target_resource.get("lineOfBusiness") or [])
            target_tags = set(target_resource.get("tags") or [])

            scored = []
            target_oid = target_resource.get("ordId", "")
            for r in resources:
                oid = r.get("ordId", "")
                if oid == target_oid: continue
                if oid in tried_candidates: continue
                # Skip candidates already modified for this target (avoids HIGH↔MEDIUM oscillation)
                if (target_oid, oid) in modified_pairs: continue
                if _tier_of(_pairwise_sim(target_resource, r, idf2, tfidf2)[0]) == target_tier: continue
                if r.get("_rtype") not in ("agent", "apiResource", "dataProduct"): continue

                # Simulate: what score if we aligned r's ET+LoB+tags to target?
                import copy
                r_sim = copy.copy(r)
                # Align ET to target (same rtype field)
                rtype = r.get("_rtype", "")
                if rtype == "agent":
                    r_sim["relatedEntityTypes"] = list(target_ets)
                elif rtype == "apiResource":
                    r_sim["exposedEntityTypes"] = [{"ordId": e} for e in target_ets]
                elif rtype == "dataProduct":
                    r_sim["entityTypes"] = list(target_ets)
                r_sim["lineOfBusiness"] = list(target_lob)
                r_sim["tags"] = list(target_tags | set(r.get("tags") or []))
                pot_sim, _ = _pairwise_sim(target_resource, r_sim, idf2, tfidf2)
                scored.append((pot_sim, oid))

            scored.sort(key=lambda x: -x[0])
            if not scored:
                break
            current_candidate_id = scored[0][1]
            tried_candidates.add(current_candidate_id)

            for _ in range(1, 4):  # up to 3 attempts per candidate
                attempt += 1
                candidate = generator_act(
                    target=target_resource,
                    tier=target_tier,
                    landscape=resources,
                    attempt=attempt,
                    existing_neighbor_ids=existing_neighbor_ids,
                    prev_breakdown=prev_breakdown,
                    systems_dir=systems_dir,
                    candidate_ordid=current_candidate_id,
                )

                if candidate is None:
                    print(f"    attempt {attempt}: Generator returned no valid JSON")
                    continue

                action = candidate.get("_action", "modify")
                print(f"    attempt {attempt}: ordId={candidate.get('ordId')} (modifies={candidate.get('_modifies')})")

                # C1: spec check (deterministic, zero LLM cost on failure)
                passed, spec_errors = spec_check(candidate)
                if not passed:
                    print(f"      C1 FAIL — {spec_errors[:2]}")
                    log_action({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "phase": "enrichment",
                        "action": action,
                        "outcome": "rejected_c1",
                        "target_resource": target_entry["ordId"],
                        "tier_target": target_tier,
                        "attempt": attempt,
                        "spec_errors": spec_errors,
                        "decision_reason": candidate.get("_decision_reason", ""),
                    }, LOG_PATH)
                    prev_breakdown = None
                    continue

                # Solver: compute similarity deterministically
                sim, breakdown = _pairwise_sim(target_resource, candidate, idf, tfidf)
                prev_breakdown = breakdown
                tier_actual = _tier_of(sim)

                if tier_actual != target_tier:
                    print(f"      score {sim:.3f} → {tier_actual or 'none'}, wanted {target_tier}  [{_format_breakdown(breakdown)}]")
                    log_action({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "phase": "enrichment",
                        "action": action,
                        "outcome": "wrong_tier",
                        "target_resource": target_entry["ordId"],
                        "tier_target": target_tier,
                        "tier_actual": tier_actual,
                        "achieved_sim": sim,
                        "attempt": attempt,
                        "solver_breakdown": breakdown,
                        "decision_reason": candidate.get("_decision_reason", ""),
                        "field_strategy": candidate.get("_field_strategy", ""),
                    }, LOG_PATH)
                    continue

                # C2-C5: Judge
                accepted, reason, verdict, judge_tokens = judge_evaluate(
                    resource=candidate,
                    target=target_resource,
                    tier=target_tier,
                    achieved_sim=sim,
                    breakdown=breakdown,
                    action=action,
                )

                log_action({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "phase": "enrichment",
                    "action": action,
                    "outcome": "accepted" if accepted else "rejected_judge",
                    "target_resource": target_entry["ordId"],
                    "tier_filled": target_tier if accepted else None,
                    "modifies_ordId": candidate.get("_modifies"),
                    "new_or_modified_ordId": candidate.get("ordId"),
                    "achieved_sim": sim,
                    "decision_reason": candidate.get("_decision_reason", ""),
                    "field_strategy": candidate.get("_field_strategy", ""),
                    "solver_breakdown": breakdown,
                    "judge_verdict": verdict,
                    "judge_reason": reason,
                    "generator_tokens": candidate.get("_generator_tokens", 0),
                    "judge_tokens": judge_tokens,
                    "attempt": attempt,
                }, LOG_PATH)

                if accepted:
                    if candidate.get("_modifies"):
                        resources = [r for r in resources if r.get("ordId") != candidate["_modifies"]]
                        _replace_resource_on_disk(candidate, systems_dir)
                    else:
                        save_resource(candidate, systems_dir)
                    resources.append(candidate)
                    # Record this (target, candidate) pair as modified — prevents oscillation
                    modified_pairs.add((target_entry["ordId"], current_candidate_id))
                    print(f"      ACCEPTED (sim={sim:.3f})")
                    success = True
                    break
                else:
                    print(f"      Judge rejected — {reason}")

            if success:
                break  # exit cand_idx loop

        if not success:
            log_action({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase": "enrichment",
                "action": "skip",
                "outcome": "tier_skip",
                "target_resource": target_entry["ordId"],
                "tier_target": target_tier,
                "max_attempts": max_attempts,
            }, LOG_PATH)
            print(f"  ✗ tier_skip: could not fill {target_tier} for {target_entry['ordId']}")
            skipped.add((target_entry["ordId"], target_tier))


def _tier_of(sim: float) -> str | None:
    if sim >= HIGH_THRESHOLD:
        return "high"
    if sim >= MEDIUM_THRESHOLD:
        return "medium"
    if sim >= LOW_THRESHOLD:
        return "low"
    return None


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Adversarial landscape enrichment")
    parser.add_argument(
        "--systems",
        default=str(ROOT / "data" / "landscape" / "systems"),
        help="Directory containing namespace subdirs with ord.json files",
    )
    parser.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS_PER_FILL)
    args = parser.parse_args()

    systems_dir = Path(args.systems)
    if not systems_dir.exists():
        print(f"Systems directory not found: {systems_dir}")
        print("Create it first with the seed landscape.")
        sys.exit(1)

    run_enrichment(systems_dir, max_attempts=args.max_attempts)


if __name__ == "__main__":
    main()
