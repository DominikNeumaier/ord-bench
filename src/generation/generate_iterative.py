"""Iterative landscape generation — Phase 1, Step 3.

Round-based: starts from 30 seeds, generates new resources per gap until 300 total.
Key design: pre-check sim uses only structural dimensions (NO TF-IDF) → fast O(1) checks.
TF-IDF text dimension is only used in the final ambiguity report, not during generation.

Tier targets per resource: HIGH>=3 (0.50-0.75), MEDIUM>=5 (0.25-0.50), LOW>=5 (0.10-0.25)
HIGH is bounded above at 0.75 because near-duplicate reduction removes any pair
with full_sim >= 0.75 (see reduce_near_dups.py).
LOW fills automatically as landscape grows — only HIGH and MEDIUM are actively generated.

Usage:
    python3 src/generation/generate_iterative.py
    python3 src/generation/generate_iterative.py --max-rounds 20 --max-resources 300
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src import llm
from src.generation.enrich_landscape import (
    spec_check, save_resource, load_landscape, LOG_PATH, log_action,
    HIGH_THRESHOLD, MEDIUM_THRESHOLD, LOW_THRESHOLD, MIN_HIGH, MIN_MEDIUM, MIN_LOW, _tier_of,
)
from src.generation.generate_seeds import SYSTEMS, generate_package
from src.adversarial.preselect import _pairwise_sim, _et_idf, _build_tfidf_index

ITERATIVE_MODEL  = "anthropic--claude-4.5-haiku"
RTYPE_TARGETS    = {"apiResource": 0.50, "agent": 0.25, "dataProduct": 0.25}
NEAR_DUPLICATE_THRESHOLD = 0.75  # fast_sim above this → treat as near-duplicate, reject C3

# ── Domain clusters ───────────────────────────────────────────────────────────

DOMAIN_CLUSTERS = {
    "hr":           {"sap.sf", "workday.hcm"},
    "procurement":  {"sap.ariba", "sap.s4"},
    "sales":        {"sap.crm", "emarsys.cx"},
    "manufacturing":{"my.mes", "sap.s4", "siemens.plm"},
    "ehs":          {"sap.ehs", "sap.s4"},
    "itsm":         {"corp.itsm", "sap.sf"},
    "plm":          {"siemens.plm", "sap.s4"},
    "cx":           {"emarsys.cx", "sap.crm"},
}

BRIDGE_ET_IDS = {
    "sap.odm:entityType:Supplier:v1",
    "sap.odm:entityType:Project:v1",
    "sap.odm:entityType:Document:v1",
    "sap.odm:entityType:Approval:v1",
    "sap.odm:entityType:Budget:v1",
    "sap.odm:entityType:Task:v1",
    "sap.odm:entityType:Location:v1",
    "sap.odm:entityType:Notification:v1",
    "sap.odm:entityType:Compliance:v1",
    "sap.odm:entityType:Report:v1",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _cluster_of(ns: str) -> str | None:
    for c, systems in DOMAIN_CLUSTERS.items():
        if ns in systems: return c
    return None

def _related_systems(ns: str, exclude: set[str]) -> list[str]:
    c = _cluster_of(ns)
    same = [s for s in DOMAIN_CLUSTERS.get(c, set()) if s != ns and s not in exclude] if c else []
    return same or [s for s in SYSTEMS if s != ns and s not in exclude]

def _different_systems(ns: str, exclude: set[str]) -> list[str]:
    c = _cluster_of(ns)
    result = [s for s in SYSTEMS if s != ns and s not in exclude
              and not (c and s in DOMAIN_CLUSTERS.get(c, set()))]
    return result or [s for s in SYSTEMS if s != ns and s not in exclude]

def _choose_rtype(resources: list[dict]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for r in resources:
        if r.get("_rtype") in RTYPE_TARGETS: counts[r["_rtype"]] += 1
    total = sum(counts.values()) or 1
    return max(RTYPE_TARGETS, key=lambda rt: RTYPE_TARGETS[rt] - counts[rt] / total)

def _get_et_ids(r: dict) -> set[str]:
    ids: set[str] = set()
    for et in (r.get("relatedEntityTypes") or []):
        ids.add(et if isinstance(et, str) else et.get("ordId", ""))
    for et in (r.get("exposedEntityTypes") or []):
        ids.add(et if isinstance(et, str) else et.get("ordId", ""))
    for et in (r.get("entityTypes") or []):
        ids.add(et if isinstance(et, str) else et.get("ordId", ""))
    ids.discard("")
    return ids

def _get_all_et_ids(systems_dir: Path) -> set[str]:
    p = systems_dir / "sap.odm" / "ord.json"
    return {e["ordId"] for e in json.loads(p.read_text()).get("entityTypes", [])} if p.exists() else set()

def _needs(counts: dict[str, int]) -> dict[str, int]:
    return {
        "high":   max(0, MIN_HIGH   - counts["high"]),
        "medium": max(0, MIN_MEDIUM - counts["medium"]),
        "low":    max(0, MIN_LOW    - counts["low"]),
    }

# ── Fast sim (no TF-IDF) ──────────────────────────────────────────────────────

def _fast_sim(a: dict, b: dict, idf: dict) -> float:
    """Sim using only structural dimensions (localId, ET, LoB, tags, industry).
    Text=0 (no TF-IDF). Conservative lower bound — real sim with text >= this.
    O(1) per call: no corpus-level index needed.
    """
    return _pairwise_sim(a, b, idf, {})[0]

# ── Profile builder ───────────────────────────────────────────────────────────

def _dummy(et_ids: set[str], lob: list[str], tags: list[str],
           rtype: str, namespace: str) -> dict:
    d: dict = {
        "_rtype": rtype, "namespace": namespace,
        "ordId": f"{namespace}:{rtype}:Dummy:v1",
        "title": "", "shortDescription": "", "description": "",
        "lineOfBusiness": list(lob), "tags": list(tags), "industry": [],
    }
    if rtype == "agent":
        d["relatedEntityTypes"] = sorted(et_ids)
    elif rtype == "apiResource":
        d["exposedEntityTypes"] = [{"ordId": e} for e in sorted(et_ids)]
        d["apiProtocol"] = "rest"; d["resourceDefinitions"] = []
    elif rtype == "dataProduct":
        d["entityTypes"] = sorted(et_ids)
        d["type"] = "primary"; d["category"] = "business-object"; d["outputPorts"] = []
    return d

def _build_profile(
    target: dict, tier: str, rtype: str, namespace: str,
    idf: dict, all_et_ids: set[str],
) -> tuple[set[str], list[str], list[str], float] | None:
    """Return (et_ids, lob, tags, sim) that lands in tier, or None."""
    target_et  = _get_et_ids(target)
    target_lob = list(target.get("lineOfBusiness") or [])
    target_tags = list(target.get("tags") or [])

    def try_profile(et, lob, tags):
        d = _dummy(et, lob, tags, rtype, namespace)
        sim = _fast_sim(target, d, idf)
        return sim

    if tier == "high":
        et = target_et.copy()
        lob = target_lob.copy()
        for tags in [target_tags, []]:
            sim = try_profile(et, lob, tags)
            if sim >= HIGH_THRESHOLD: return et, lob, tags, sim
        return None

    elif tier == "medium":
        # Strategy 1: 2+ shared ETs, different LoB
        if len(target_et) >= 2:
            et = set(list(target_et)[:2])
            for lob in [[], ["Finance"], ["Operations"]]:
                sim = try_profile(et, lob, [])
                if MEDIUM_THRESHOLD <= sim < HIGH_THRESHOLD: return et, lob, [], sim
        # Strategy 2: all ETs, different LoB
        et = target_et.copy()
        for lob in [[], ["Finance"], ["Operations"], ["Manufacturing"]]:
            if lob != target_lob:
                sim = try_profile(et, lob, [])
                if MEDIUM_THRESHOLD <= sim < HIGH_THRESHOLD: return et, lob, [], sim
        # Strategy 3: same namespace, 1+ ETs, same LoB (no cross-ns bonus)
        if namespace == target.get("namespace"):
            for n in range(1, len(target_et) + 1):
                et = set(list(target_et)[:n])
                sim = try_profile(et, target_lob, [])
                if MEDIUM_THRESHOLD <= sim < HIGH_THRESHOLD: return et, target_lob, [], sim
        # Strategy 4: 1 ET, same LoB
        for et_id in sorted(target_et):
            sim = try_profile({et_id}, target_lob, [])
            if MEDIUM_THRESHOLD <= sim < HIGH_THRESHOLD: return {et_id}, target_lob, [], sim
        # Strategy 5: Bridge ETs
        for bridge in BRIDGE_ET_IDS:
            et = (target_et & {bridge}) or {bridge}
            for lob in [[], target_lob]:
                sim = try_profile(et, lob, [])
                if MEDIUM_THRESHOLD <= sim < HIGH_THRESHOLD: return et, lob, [], sim
        return None

    elif tier == "low":
        # Different rtype + 1 shared ET → type penalty keeps it LOW
        alt = {"agent": "apiResource", "apiResource": "dataProduct", "dataProduct": "agent"}[rtype]
        for et_id in sorted(target_et)[:3]:
            d = _dummy({et_id}, [], [], alt, namespace)
            sim = _fast_sim(target, d, idf)
            if LOW_THRESHOLD <= sim < MEDIUM_THRESHOLD: return {et_id}, [], [], sim
        # Non-shared ET, same rtype
        for et_id in sorted(all_et_ids - target_et)[:10]:
            sim = try_profile({et_id}, [], [])
            if LOW_THRESHOLD <= sim < MEDIUM_THRESHOLD: return {et_id}, [], [], sim
        return None

    return None

# ── Prompts ───────────────────────────────────────────────────────────────────

_GEN_SYS = """You are an ORD resource designer for enterprise software benchmarks.
Generate ONE realistic ORD resource JSON for the given system and type.
ALL systems use sap.odm:entityType:* IDs — including non-SAP systems.
Description must naturally reflect the entity types WITHOUT explicitly naming the resource type:
  agent → action verbs (monitors, automates, coordinates, processes)
  apiResource → data verbs (exposes, retrieves, manages, provides access to)
  dataProduct → analytical verbs (aggregates, summarizes, provides metrics on)
ALL semantic fields must be non-empty. Respond with ONLY valid JSON."""

_JUDGE_SYS = """You are a benchmark quality judge for ORD resources (synthetic ambiguity benchmark).
C1 (spec) already passed. Evaluate C2–C5.
ALL systems use sap.odm:entityType:* IDs — never reject for this.

CRITICAL: This benchmark intentionally creates cross-domain resources to build ambiguity.
Cross-domain entity types are CORRECT AND DESIRED.

ACCEPT if the resource makes any reasonable sense for the system.
ACCEPT cross-domain ET references if ANY connection exists (e.g. HR+Compliance, ITSM+Project).
REJECT only if: completely absurd for the system, OR exact functional duplicate (same title+scope).

Respond with ONLY a JSON object."""

def _gen_prompt(ns: str, domain: str, rtype: str, et_ids: set[str],
                lob: list[str], tags: list[str], existing: list[str]) -> str:
    et_names = [e.split(":")[2] for e in sorted(et_ids) if e.count(":") >= 2]
    et_field = {
        "agent":       f'"relatedEntityTypes": {json.dumps(sorted(et_ids))}',
        "apiResource": (f'"exposedEntityTypes": {json.dumps([{"ordId": e} for e in sorted(et_ids)])},'
                        f'\n  "apiProtocol": "rest",'
                        f'\n  "resourceDefinitions": [{{"type":"openapi-v3","mediaType":"application/json",'
                        f'"url":"/api/v1/placeholder.json","accessStrategies":[{{"type":"open"}}]}}]'),
        "dataProduct": (f'"entityTypes": {json.dumps(sorted(et_ids))},'
                        f'\n  "type": "primary", "category": "business-object",'
                        f'\n  "outputPorts": [{{"ordId":"{ns}:apiResource:Placeholder:v1"}}]'),
    }[rtype]
    existing_str = "\n".join(f"  - {o}" for o in existing[-8:]) or "  none"
    lob_val = json.dumps(lob) if lob else '["<domain-name>"]'
    tags_val = json.dumps(tags) if tags else '["<tag1>","<tag2>","<tag3>"]'
    return f"""System: {ns} — {domain}
Resource type: {rtype}
Entity types to reference (use ALL): {', '.join(et_names)}
lineOfBusiness: {lob_val}  tags: {tags_val}
Existing in this system (must differ): {existing_str}

Generate:
{{
  "ordId": "{ns}:{rtype}:<PascalCaseName>:v1",
  "title": "<clear title>",
  "shortDescription": "<one sentence, max 120 chars>",
  "description": "<2-3 sentences using appropriate verbs for {rtype}>",
  "version": "1.0.0", "lastUpdate": "2026-06-07T00:00:00+00:00",
  "visibility": "public", "releaseStatus": "active",
  "partOfPackage": "{ns}:package:Core:v1",
  {et_field},
  "lineOfBusiness": {lob_val},
  "tags": {tags_val},
  "industry": []
}}"""

def _judge_prompt(resource: dict, ns: str, domain: str, existing: list[str]) -> str:
    existing_str = "\n".join(f"  - {o}" for o in existing[-8:]) or "  none"
    return f"""Evaluate for {ns} ({domain}).
Resource: {json.dumps({k:v for k,v in resource.items() if not k.startswith("_")}, indent=2)}
Existing: {existing_str}
Respond: {{"c2_coherent":bool,"c2_reason":"...","c3_not_duplicate":bool,"c3_reason":"...","c4_et_justified":bool,"c4_reason":"...","c5_ok":bool,"c5_reason":"...","accepted":bool,"reject_reason":"if rejected"}}"""

# ── Main loop ─────────────────────────────────────────────────────────────────

def run_iterative(systems_dir: Path, max_rounds: int = 20, max_resources: int = 300) -> None:
    print(f"Iterative landscape generation")
    print(f"Model: {ITERATIVE_MODEL}  |  Target: {max_resources}  |  Max rounds: {max_rounds}\n")

    all_et_ids = _get_all_et_ids(systems_dir)
    print(f"Entity types available: {len(all_et_ids)}")

    # Persistent tier counts — updated incrementally (fast_sim, no TF-IDF)
    tier_counts_map: dict[str, dict[str, int]] = {}

    def _init_tier_map(all_res: list[dict]) -> None:
        """Bulk-initialise tier_counts_map for all resources not yet tracked.
        Uses upper-triangle: each pair computed once, idf built once.
        """
        idf_local = _et_idf(all_res)
        rt = {"agent", "apiResource", "dataProduct"}
        rt_res = [r for r in all_res if r.get("_rtype") in rt]
        new_res = [r for r in rt_res if r["ordId"] not in tier_counts_map]
        if not new_res:
            return
        # Ensure entries exist
        for r in rt_res:
            if r["ordId"] not in tier_counts_map:
                tier_counts_map[r["ordId"]] = {"high": 0, "medium": 0, "low": 0}
        # Compute pairs involving new resources only (against all rt_res)
        new_oids = {r["ordId"] for r in new_res}
        for i, r in enumerate(rt_res):
            for other in rt_res[i+1:]:
                if r["ordId"] not in new_oids and other["ordId"] not in new_oids:
                    continue  # skip pairs where neither is new
                sim = _fast_sim(r, other, idf_local)
                t = _tier_of(sim)
                if t:
                    tier_counts_map[r["ordId"]][t]     += 1
                    tier_counts_map[other["ordId"]][t] += 1

    def _add_to_tier_map(new_resource: dict, all_res: list[dict]) -> None:
        """Add ONE new resource to tier_counts_map. idf built once."""
        idf_local = _et_idf(all_res)
        oid = new_resource["ordId"]
        if oid not in tier_counts_map:
            tier_counts_map[oid] = {"high": 0, "medium": 0, "low": 0}
        rt = {"agent", "apiResource", "dataProduct"}
        for other in all_res:
            if other.get("_rtype") not in rt: continue
            if other["ordId"] == oid: continue
            sim = _fast_sim(new_resource, other, idf_local)
            t = _tier_of(sim)
            if t:
                tier_counts_map[oid][t] += 1
                if other["ordId"] not in tier_counts_map:
                    tier_counts_map[other["ordId"]] = {"high": 0, "medium": 0, "low": 0}
                tier_counts_map[other["ordId"]][t] += 1

    for rnd in range(1, max_rounds + 1):
        resources = load_landscape(systems_dir)
        n = len([r for r in resources if r.get("_rtype") in ("agent","apiResource","dataProduct")])
        print(f"\n{'='*60}")
        print(f"ROUND {rnd}  |  {n}/{max_resources} resources")

        if n >= max_resources:
            print(f"  Target reached — stopping.")
            break

        # Bulk-init tier_counts_map for any resources not yet tracked
        _init_tier_map(resources)

        # Compute gaps
        gaps: list[tuple[str, str]] = []
        for r in resources:
            if r.get("_rtype") not in ("agent","apiResource","dataProduct"): continue
            tc = tier_counts_map.get(r["ordId"], {"high":0,"medium":0,"low":0})
            nd = _needs(tc)
            for tier in ("high", "medium"):
                for _ in range(nd[tier]):
                    gaps.append((r["ordId"], tier))

        # Sort: all HIGH gaps before all MEDIUM gaps
        # Rationale: resources generated for HIGH may already satisfy MEDIUM for other targets,
        # reducing total generations needed.
        high_gaps   = [(oid, t) for oid, t in gaps if t == "high"]
        medium_gaps = [(oid, t) for oid, t in gaps if t == "medium"]
        unique_gaps = list(dict.fromkeys(high_gaps + medium_gaps))

        sat = sum(1 for tc in tier_counts_map.values()
                  if tc["high"] >= MIN_HIGH and tc["medium"] >= MIN_MEDIUM and tc["low"] >= MIN_LOW)
        print(f"  Gaps: {len(unique_gaps)} ({len(high_gaps)} H, {len(medium_gaps)} M)  |  "
              f"Satisfied: {sat}/{len(tier_counts_map)}")

        round_accepted = 0
        round_added: list[dict] = []
        # Build idf once per round — rebuilt only after each accept
        idf_now = _et_idf(resources)

        round_accepted = 0
        round_added: list[dict] = []
        # Build idf once per round — rebuilt only after each accept
        idf_now = _et_idf(resources)

        for target_ordid, tier in unique_gaps:
            if n + len(round_added) >= max_resources:
                print(f"  Hit max_resources — stopping round.")
                break

            # Re-check: maybe already filled by earlier addition this round
            all_now = resources + round_added
            target_res = next((r for r in all_now if r.get("ordId") == target_ordid), None)
            if target_res is None: continue

            current_count = sum(
                1 for r in all_now
                if r.get("ordId") != target_ordid
                and r.get("_rtype") in ("agent","apiResource","dataProduct")
                and _tier_of(_fast_sim(target_res, r, idf_now)) == tier
            )
            if current_count >= {"high": MIN_HIGH, "medium": MIN_MEDIUM, "low": MIN_LOW}[tier]:
                continue

            # Choose rtype and namespace
            rtype = _choose_rtype(all_now)
            target_ns = target_res.get("namespace","")

            # Count resources per system to enforce balance
            per_ns_count: dict[str, int] = defaultdict(int)
            for r in all_now:
                if r.get("_rtype") in ("agent","apiResource","dataProduct"):
                    per_ns_count[r.get("namespace","")] += 1
            cap = (max_resources + len(SYSTEMS) - 1) // len(SYSTEMS)  # ceil division: 300/10=30

            if tier == "high":
                ns_candidates = _related_systems(target_ns, {target_ns})
            else:
                ns_candidates = _different_systems(target_ns, {target_ns})
            ns_candidates += [s for s in SYSTEMS if s not in ns_candidates and s != target_ns]

            # Sort by fewest resources first — balances landscape across systems
            # Skip systems already at cap
            ns_order = [ns for ns in ns_candidates if per_ns_count[ns] < cap]
            ns_order.sort(key=lambda ns: per_ns_count[ns])
            if not ns_order:
                # All related systems at cap — allow any system under cap
                ns_order = sorted([s for s in SYSTEMS if s != target_ns and per_ns_count[s] < cap],
                                  key=lambda ns: per_ns_count[ns])
            if not ns_order:
                continue  # all systems at cap, can't place new resource

            # Find profile (pre-check, no LLM)
            profile = None
            namespace = target_ns
            for try_ns in ns_order:
                p = _build_profile(target_res, tier, rtype, try_ns, idf_now, all_et_ids)
                if p:
                    profile = p; namespace = try_ns; break

            if profile is None:
                log_action({"timestamp": datetime.now(timezone.utc).isoformat(),
                            "phase":"iterative","round":rnd,"action":"skip",
                            "outcome":"no_profile","target_resource":target_ordid,
                            "tier_target":tier,"rtype":rtype}, LOG_PATH)
                continue

            et_ids, lob, tags, pre_sim = profile
            generate_package(namespace, systems_dir)
            existing_oids = [r["ordId"] for r in all_now if r.get("namespace") == namespace]

            # Generator
            domain = SYSTEMS.get(namespace, namespace)
            prompt = _gen_prompt(namespace, domain, rtype, et_ids, lob, tags, existing_oids)
            text, gen_meta = llm.chat(prompt, system=_GEN_SYS, model=ITERATIVE_MODEL)
            m = re.search(r"\{[\s\S]*\}", text)
            if not m: continue
            try:
                resource = json.loads(m.group(0))
            except json.JSONDecodeError:
                continue

            resource["_rtype"] = rtype
            resource["namespace"] = namespace
            # Enforce ET and LoB from profile
            if rtype == "agent":       resource["relatedEntityTypes"] = sorted(et_ids)
            elif rtype == "apiResource": resource["exposedEntityTypes"] = [{"ordId":e} for e in sorted(et_ids)]
            elif rtype == "dataProduct": resource["entityTypes"] = sorted(et_ids)
            if lob: resource["lineOfBusiness"] = lob

            # C1
            passed, spec_errors = spec_check(resource)
            if not passed:
                log_action({"timestamp": datetime.now(timezone.utc).isoformat(),
                            "phase":"iterative","round":rnd,"action":"create",
                            "outcome":"rejected_c1","target_resource":target_ordid,
                            "tier_target":tier,"spec_errors":spec_errors}, LOG_PATH)
                continue

            # Solver verify (fast_sim — consistent with pre-check)
            sim = _fast_sim(target_res, resource, idf_now)
            tier_actual = _tier_of(sim)
            if tier_actual != tier:
                log_action({"timestamp": datetime.now(timezone.utc).isoformat(),
                            "phase":"iterative","round":rnd,"action":"create",
                            "outcome":"wrong_tier","target_resource":target_ordid,
                            "tier_target":tier,"tier_actual":tier_actual,
                            "achieved_sim":sim,"pre_check_sim":pre_sim}, LOG_PATH)
                continue

            # Near-duplicate check (fast_sim ≥ 0.75 against ANY existing resource = reject)
            max_sim_existing = max(
                (_fast_sim(resource, r, idf_now) for r in all_now
                 if r.get("ordId") != resource.get("ordId")
                 and r.get("_rtype") in ("agent","apiResource","dataProduct")),
                default=0.0
            )
            if max_sim_existing >= NEAR_DUPLICATE_THRESHOLD:
                log_action({"timestamp": datetime.now(timezone.utc).isoformat(),
                            "phase":"iterative","round":rnd,"action":"create",
                            "outcome":"near_duplicate","target_resource":target_ordid,
                            "tier_target":tier,"max_sim_existing":max_sim_existing}, LOG_PATH)
                print(f"  [{rnd}] NEAR-DUP {tier:6s} max_sim={max_sim_existing:.3f}  {resource.get('ordId')}")
                continue

            # C2-C5 Judge
            jp = _judge_prompt(resource, namespace, domain, existing_oids)
            jtext, j_meta = llm.chat(jp, system=_JUDGE_SYS, model=ITERATIVE_MODEL)
            jm = re.search(r"\{[\s\S]*\}", jtext)
            if not jm: continue
            try:
                verdict = json.loads(jm.group(0))
            except json.JSONDecodeError:
                continue

            accepted = verdict.get("accepted", False)
            log_action({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase":"iterative","round":rnd,"action":"create",
                "outcome":"accepted" if accepted else "rejected_judge",
                "target_resource":target_ordid,"tier_target":tier,
                "achieved_sim":sim,"pre_check_sim":pre_sim,
                "profile":{"et_ids":sorted(et_ids),"lob":lob,"rtype":rtype,"namespace":namespace},
                "judge_verdict":verdict,
                "generator_tokens":gen_meta.get("tokens",0),
                "judge_tokens":j_meta.get("tokens",0),
            }, LOG_PATH)

            if accepted:
                save_resource(resource, systems_dir)
                round_added.append(resource)
                _add_to_tier_map(resource, resources + round_added)
                idf_now = _et_idf(resources + round_added)  # rebuild once after accept
                round_accepted += 1
                print(f"  [{rnd}] ACCEPTED {tier:6s} sim={sim:.3f}  {resource.get('ordId')}")
            else:
                reason = verdict.get("reject_reason","")
                print(f"  [{rnd}] REJECTED {tier:6s} sim={sim:.3f}  {reason[:70]}")

        print(f"\n  Round {rnd}: {round_accepted} accepted → {n + round_accepted} total")

        # Milestone report every 50 resources
        n_now = n + round_accepted
        if n_now >= 50 and n_now % 50 < round_accepted or (n_now >= 50 and round_accepted > 0 and n_now // 50 > n // 50):
            sat = sum(1 for tc in tier_counts_map.values()
                      if tc["high"] >= MIN_HIGH and tc["medium"] >= MIN_MEDIUM and tc["low"] >= MIN_LOW)
            sat_h = sum(1 for tc in tier_counts_map.values() if tc["high"]   >= MIN_HIGH)
            sat_m = sum(1 for tc in tier_counts_map.values() if tc["medium"] >= MIN_MEDIUM)
            sat_l = sum(1 for tc in tier_counts_map.values() if tc["low"]    >= MIN_LOW)
            print(f"\n  ── MILESTONE: {n_now} resources ──────────────────────────────")
            print(f"  Satisfied — HIGH: {sat_h}/{len(tier_counts_map)}  "
                  f"MEDIUM: {sat_m}/{len(tier_counts_map)}  "
                  f"LOW: {sat_l}/{len(tier_counts_map)}  "
                  f"ALL: {sat}/{len(tier_counts_map)}")
            print(f"  ─────────────────────────────────────────────────────────────")

        if round_accepted == 0:
            print("  No progress — continuing.")

    # Final stats
    resources = load_landscape(systems_dir)
    rt_res = [r for r in resources if r.get("_rtype") in ("agent","apiResource","dataProduct")]
    idf_f = _et_idf(resources)
    tfidf_f = _build_tfidf_index(resources)  # full TF-IDF only for final report

    high_p = med_p = low_p = 0
    final_map: dict[str, dict[str, int]] = {}
    for i, r in enumerate(rt_res):
        h = m = l = 0
        for j, o in enumerate(rt_res):
            if i == j: continue
            sim, _ = _pairwise_sim(r, o, idf_f, tfidf_f)
            t = _tier_of(sim)
            if t == "high": h += 1
            elif t == "medium": m += 1
            elif t == "low": l += 1
        final_map[r["ordId"]] = {"high":h,"medium":m,"low":l}
        high_p += h; med_p += m; low_p += l
    high_p //= 2; med_p //= 2; low_p //= 2

    counts: dict[str, int] = defaultdict(int)
    for r in resources: counts[r.get("_rtype","?")] += 1

    sat_h = sum(1 for tc in final_map.values() if tc["high"]   >= MIN_HIGH)
    sat_m = sum(1 for tc in final_map.values() if tc["medium"] >= MIN_MEDIUM)
    sat_l = sum(1 for tc in final_map.values() if tc["low"]    >= MIN_LOW)
    done  = sum(1 for tc in final_map.values()
                if tc["high"]>=MIN_HIGH and tc["medium"]>=MIN_MEDIUM and tc["low"]>=MIN_LOW)

    print(f"\n{'='*60}")
    print(f"ITERATIVE GENERATION COMPLETE")
    print(f"Total: {len(resources)}  (API={counts['apiResource']} Agent={counts['agent']} DP={counts['dataProduct']})")
    print(f"Pairs — HIGH:{high_p}  MEDIUM:{med_p}  LOW:{low_p}")
    print(f"Satisfied (H≥{MIN_HIGH} M≥{MIN_MEDIUM} L≥{MIN_LOW}):  HIGH:{sat_h}  MEDIUM:{sat_m}  LOW:{sat_l}  ALL:{done}/{len(final_map)}")
    print(f"Log: {LOG_PATH}")


def main() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--systems", default=str(ROOT/"data"/"landscape"/"systems"))
    p.add_argument("--max-rounds", type=int, default=20)
    p.add_argument("--max-resources", type=int, default=300)
    args = p.parse_args()
    run_iterative(Path(args.systems), args.max_rounds, args.max_resources)


if __name__ == "__main__":
    main()
