"""Near-duplicate cleanup for the benchmark landscape.

For each pair with full_sim >= 0.75:
  - If one resource already has >= 3 HIGH neighbors (excl. its near-dup partner) → remove it
  - Otherwise → rewrite the resource via LLM to lower text similarity
  - If rewrite fails after 3 attempts → remove it

Usage:
    python3 src/generation/reduce_near_dups.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src import llm
from src.generation.enrich_landscape import (
    load_landscape, log_action, LOG_PATH, spec_check,
    HIGH_THRESHOLD, MIN_HIGH,
)
from src.adversarial.preselect import _pairwise_sim, _et_idf, _build_tfidf_index

DEDUP_MODEL   = "anthropic--claude-4.5-haiku"
NEAR_DUP_THRESHOLD = 0.75

_REWRITE_SYS = """You are an ORD resource editor. Rewrite a resource's title, shortDescription,
description, and tags so it is LESS textually similar to a given reference resource —
while keeping the same entity types, lineOfBusiness, system domain, and overall function.
Change vocabulary, sentence structure, and focus angle. The resource must remain a coherent,
realistic enterprise resource for its system.
Respond with ONLY a JSON object containing the rewritten fields."""


def _full_sim(a: dict, b: dict, idf: dict, tfidf: dict) -> float:
    return _pairwise_sim(a, b, idf, tfidf)[0]


def _high_neighbors(resource: dict, all_rt: list[dict],
                    idf: dict, tfidf: dict, exclude_oid: str) -> int:
    """Count HIGH neighbors of resource, excluding exclude_oid."""
    return sum(
        1 for other in all_rt
        if other["ordId"] != resource["ordId"]
        and other["ordId"] != exclude_oid
        and HIGH_THRESHOLD <= _full_sim(resource, other, idf, tfidf) < NEAR_DUP_THRESHOLD
    )


def _remove_from_disk(oid: str, systems_dir: Path) -> bool:
    ns = oid.split(":")[0]
    p = systems_dir / ns / "ord.json"
    if not p.exists():
        return False
    doc = json.loads(p.read_text())
    for key in ("agents", "apiResources", "dataProducts"):
        before = len(doc.get(key, []))
        doc[key] = [r for r in doc.get(key, []) if r.get("ordId") != oid]
        if len(doc[key]) < before:
            p.write_text(json.dumps(doc, indent=2))
            return True
    return False


def _replace_on_disk(resource: dict, systems_dir: Path) -> None:
    ns = resource.get("namespace", resource["ordId"].split(":")[0])
    p = systems_dir / ns / "ord.json"
    if not p.exists():
        return
    doc = json.loads(p.read_text())
    rtype = resource.get("_rtype", "")
    key = {"agent": "agents", "apiResource": "apiResources", "dataProduct": "dataProducts"}.get(rtype, "apiResources")
    clean = {k: v for k, v in resource.items() if not k.startswith("_")}
    arr = doc.get(key, [])
    for i, r in enumerate(arr):
        if r.get("ordId") == resource["ordId"]:
            arr[i] = clean
            p.write_text(json.dumps(doc, indent=2))
            return


def _rewrite_resource(resource: dict, reference: dict, idf: dict, tfidf: dict,
                      systems_dir: Path) -> dict | None:
    """Try to rewrite resource so full_sim(resource, reference) < NEAR_DUP_THRESHOLD."""
    ns = resource.get("namespace", resource["ordId"].split(":")[0])
    from src.generation.generate_seeds import SYSTEMS
    domain = SYSTEMS.get(ns, ns)

    for attempt in range(1, 4):
        prompt = f"""Rewrite this ORD resource to be LESS textually similar to the reference below.
Change: title, shortDescription, description, tags
Keep unchanged: ordId, entityTypes, lineOfBusiness, partOfPackage, visibility, releaseStatus, version, apiProtocol, resourceDefinitions, outputPorts, type, category

REFERENCE (make the rewrite differ from this):
  title: {reference.get("title", "")}
  shortDescription: {reference.get("shortDescription", "")}
  description: {reference.get("description", "")}
  tags: {reference.get("tags", [])}

RESOURCE TO REWRITE:
  ordId: {resource["ordId"]}
  system: {ns} ({domain})
  title: {resource.get("title", "")}
  shortDescription: {resource.get("shortDescription", "")}
  description: {resource.get("description", "")}
  tags: {resource.get("tags", [])}

Return JSON with only these fields:
{{"title": "...", "shortDescription": "...", "description": "...", "tags": [...]}}"""

        text, _ = llm.chat(prompt, system=_REWRITE_SYS, model=DEDUP_MODEL)
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            continue
        try:
            patch = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue

        rewritten = dict(resource)
        for field in ("title", "shortDescription", "description", "tags"):
            if field in patch:
                rewritten[field] = patch[field]

        # Check if sim dropped below threshold
        new_sim = _full_sim(rewritten, reference, idf, tfidf)
        if new_sim < NEAR_DUP_THRESHOLD:
            # Spec check
            passed, errors = spec_check(rewritten)
            if passed:
                print(f"    attempt {attempt}: rewritten → sim={new_sim:.3f} ✓")
                return rewritten
            else:
                print(f"    attempt {attempt}: sim={new_sim:.3f} but C1 fail: {errors[:1]}")
        else:
            print(f"    attempt {attempt}: sim={new_sim:.3f} still above threshold")

    return None


def run(systems_dir: Path) -> None:
    near_dup_path = systems_dir.parent / "near_dup_pairs.json"
    if not near_dup_path.exists():
        print("near_dup_pairs.json not found — nothing to do")
        return

    pairs = json.loads(near_dup_path.read_text())
    print(f"Loaded {len(pairs)} near-duplicate pairs (full_sim >= {NEAR_DUP_THRESHOLD})")

    resources = load_landscape(systems_dir)
    rt = [r for r in resources if r.get("_rtype") in ("agent", "apiResource", "dataProduct")]
    idf   = _et_idf(resources)
    tfidf = _build_tfidf_index(resources)

    removed_oids: set[str] = set()
    rewritten_count = 0

    for pair in pairs:
        oid_a, oid_b = pair["ordId_a"], pair["ordId_b"]

        # Skip if one was already removed in a previous iteration
        if oid_a in removed_oids or oid_b in removed_oids:
            continue

        # Reload current state
        rt_current = [r for r in load_landscape(systems_dir)
                      if r.get("_rtype") in ("agent", "apiResource", "dataProduct")]
        idf_c   = _et_idf(rt_current)
        tfidf_c = _build_tfidf_index(rt_current)

        res_a = next((r for r in rt_current if r["ordId"] == oid_a), None)
        res_b = next((r for r in rt_current if r["ordId"] == oid_b), None)
        if not res_a or not res_b:
            continue

        # Verify pair is still above threshold
        sim = _full_sim(res_a, res_b, idf_c, tfidf_c)
        if sim < NEAR_DUP_THRESHOLD:
            print(f"  SKIP {oid_a.split(':')[2][:20]} / {oid_b.split(':')[2][:20]} — sim={sim:.3f} already below threshold")
            continue

        print(f"\nPair sim={sim:.3f}:")
        print(f"  A: {oid_a}")
        print(f"  B: {oid_b}")

        high_a = _high_neighbors(res_a, rt_current, idf_c, tfidf_c, oid_b)
        high_b = _high_neighbors(res_b, rt_current, idf_c, tfidf_c, oid_a)
        print(f"  HIGH neighbors: A={high_a}  B={high_b}")

        # Decision logic
        if high_a >= MIN_HIGH and high_b >= MIN_HIGH:
            # Both satisfied — remove B (second in pair)
            to_remove = oid_b
            print(f"  Both have ≥{MIN_HIGH} HIGH → removing B")
        elif high_b >= MIN_HIGH:
            # B satisfied — remove B
            to_remove = oid_b
            print(f"  B has ≥{MIN_HIGH} HIGH → removing B")
        elif high_a >= MIN_HIGH:
            # A satisfied — remove A
            to_remove = oid_a
            print(f"  A has ≥{MIN_HIGH} HIGH → removing A")
        else:
            # Neither satisfied — try to rewrite B
            to_remove = None
            print(f"  Neither satisfied → trying rewrite of B")
            rewritten = _rewrite_resource(res_b, res_a, idf_c, tfidf_c, systems_dir)
            if rewritten:
                _replace_on_disk(rewritten, systems_dir)
                rewritten_count += 1
                log_action({"timestamp": datetime.now(timezone.utc).isoformat(),
                            "phase": "dedup", "action": "rewrite",
                            "outcome": "accepted",
                            "ordId": oid_b, "near_dup_of": oid_a,
                            "original_sim": sim}, LOG_PATH)
                print(f"  Rewritten B successfully")
            else:
                to_remove = oid_b
                print(f"  Rewrite failed after 3 attempts → removing B")

        if to_remove:
            if _remove_from_disk(to_remove, systems_dir):
                removed_oids.add(to_remove)
                log_action({"timestamp": datetime.now(timezone.utc).isoformat(),
                            "phase": "dedup", "action": "remove",
                            "outcome": "removed",
                            "ordId": to_remove,
                            "near_dup_of": oid_a if to_remove == oid_b else oid_b,
                            "original_sim": sim}, LOG_PATH)
                print(f"  Removed {to_remove.split(':')[2][:30]}")

    # Final verification
    print(f"\n{'='*60}")
    print(f"DEDUP COMPLETE — {len(removed_oids)} removed, {rewritten_count} rewritten")

    resources_final = load_landscape(systems_dir)
    rt_final = [r for r in resources_final
                if r.get("_rtype") in ("agent", "apiResource", "dataProduct")]
    idf_f   = _et_idf(resources_final)
    tfidf_f = _build_tfidf_index(resources_final)

    remaining_near_dups = []
    for i, r in enumerate(rt_final):
        for other in rt_final[i+1:]:
            sim = _full_sim(r, other, idf_f, tfidf_f)
            if sim >= NEAR_DUP_THRESHOLD:
                remaining_near_dups.append((sim, r["ordId"], other["ordId"]))

    print(f"Total resources: {len(rt_final)}")
    print(f"Remaining near-dup pairs >= {NEAR_DUP_THRESHOLD}: {len(remaining_near_dups)}")

    # Update near_dup_pairs.json
    near_dup_path.write_text(json.dumps(
        [{"ordId_a": a, "ordId_b": b, "full_sim": round(s, 3)}
         for s, a, b in sorted(remaining_near_dups, reverse=True)],
        indent=2
    ))


if __name__ == "__main__":
    run(ROOT / "data" / "landscape" / "systems")
