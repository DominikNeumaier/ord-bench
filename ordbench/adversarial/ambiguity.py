"""Ambiguity scoring.

ambiguity_score = cosine_sim(prompt, distractor) / cosine_sim(prompt, correct)

Clamped to [0, 1]. Score >= 0.30 = genuine distractor.

ambiguity_profile() returns the full picture:
  - n_distractors: how many resources score >= threshold
  - mean_distractor_score: average similarity of all distractors
  - top_distractors: list of (ordId, score) for the top 3
  - structural_path: which ORD fields on the correct resource allow typed methods to find it
"""

from __future__ import annotations
import math
from src.core import llm


def _cosine(a: list[float], b: list[float]) -> float:
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return s / (na * nb)


def _resource_text(r: dict) -> str:
    parts = [r.get("title", ""), r.get("shortDescription", "")]
    caps = r.get("capabilities", [])
    if caps:
        parts.append(" ".join(caps))
    return " ".join(p for p in parts if p)


def ambiguity_score(
    prompt: str,
    correct: dict,
    distractor: dict,
) -> float:
    """Ratio of distractor similarity to correct similarity. Clamped [0,1]."""
    prompt_vec, _ = llm.embed(prompt)
    correct_vec, _ = llm.embed(_resource_text(correct))
    distractor_vec, _ = llm.embed(_resource_text(distractor))

    sim_correct = _cosine(prompt_vec, correct_vec)
    sim_distractor = _cosine(prompt_vec, distractor_vec)

    if sim_correct == 0:
        return 0.0
    return min(1.0, sim_distractor / sim_correct)


def find_best_distractor(
    prompt: str,
    correct: dict,
    all_resources: list[dict],
) -> tuple[dict | None, float]:
    """Find the resource (excluding correct) with the highest ambiguity_score."""
    prompt_vec, _ = llm.embed(prompt)
    correct_vec, _ = llm.embed(_resource_text(correct))
    sim_correct = _cosine(prompt_vec, correct_vec)

    best_resource = None
    best_score = 0.0

    for r in all_resources:
        if r["ordId"] == correct["ordId"]:
            continue
        r_vec, _ = llm.embed(_resource_text(r))
        sim_r = _cosine(prompt_vec, r_vec)
        score = min(1.0, sim_r / sim_correct) if sim_correct > 0 else 0.0
        if score > best_score:
            best_score = score
            best_resource = r

    return best_resource, round(best_score, 4)


def ambiguity_profile(
    prompt: str,
    correct: dict,
    all_resources: list[dict],
    threshold: float = 0.30,
) -> dict:
    """Full ambiguity profile: count, mean score, top distractors."""
    prompt_vec, _ = llm.embed(prompt)
    correct_vec, _ = llm.embed(_resource_text(correct))
    sim_correct = _cosine(prompt_vec, correct_vec)

    scored = []
    for r in all_resources:
        if r["ordId"] == correct["ordId"]:
            continue
        r_vec, _ = llm.embed(_resource_text(r))
        sim_r = _cosine(prompt_vec, r_vec)
        score = min(1.0, sim_r / sim_correct) if sim_correct > 0 else 0.0
        scored.append((r, round(score, 4)))

    scored.sort(key=lambda x: -x[1])
    above_threshold = [(r, s) for r, s in scored if s >= threshold]

    return {
        "n_distractors_above_threshold": len(above_threshold),
        "mean_distractor_score": round(
            sum(s for _, s in above_threshold) / len(above_threshold), 4
        ) if above_threshold else 0.0,
        "top_distractors": [
            {"ordId": r["ordId"], "title": r.get("title", ""), "score": s}
            for r, s in above_threshold[:3]
        ],
        "sim_correct": round(sim_correct, 4),
    }


def structural_solvability(correct: dict, all_resources: list[dict]) -> dict:
    """Check which ORD-typed paths lead to the correct resource.

    Returns which fields the correct resource has that typed methods can exploit,
    and whether any distractor shares those exact values (reducing typed-method advantage).
    """
    caps = set(correct.get("capabilities", []))
    entity_types = set(correct.get("entityTypes", []))
    groups = set(
        g.get("groupId") if isinstance(g, dict) else g
        for g in correct.get("partOfGroups", [])
    )
    lob = set(correct.get("lineOfBusiness", []))

    # For each field: how many other resources share it?
    def shared_count(field_values: set, field_name: str) -> dict:
        shared = []
        for r in all_resources:
            if r["ordId"] == correct["ordId"]:
                continue
            if field_name == "capabilities":
                vals = set(r.get("capabilities", []))
            elif field_name == "entityTypes":
                vals = set(r.get("entityTypes", []))
            elif field_name == "partOfGroups":
                vals = set(
                    g.get("groupId") if isinstance(g, dict) else g
                    for g in r.get("partOfGroups", [])
                )
            elif field_name == "lineOfBusiness":
                vals = set(r.get("lineOfBusiness", []))
            else:
                vals = set()
            overlap = field_values & vals
            if overlap:
                shared.append({"ordId": r["ordId"], "shared_values": sorted(overlap)})
        return {"values": sorted(field_values), "n_resources_sharing": len(shared), "sharing_resources": shared[:3]}

    return {
        "capabilities": shared_count(caps, "capabilities"),
        "entityTypes": shared_count(entity_types, "entityTypes"),
        "partOfGroups": shared_count(groups, "partOfGroups"),
        "lineOfBusiness": shared_count(lob, "lineOfBusiness"),
        "method_B_path": bool(entity_types),           # B uses entityTypes in Stage 3
        "method_C_path": bool(entity_types or groups), # C anchors on entityTypes + groups
        "method_D_path": bool(caps),                   # D uses capabilities via list_capabilities
        "solvable_by_typed_methods": bool(caps or entity_types or groups),
    }


def capability_overlap(correct: dict, distractor: dict) -> list[str]:
    caps_c = set(correct.get("capabilities", []))
    caps_d = set(distractor.get("capabilities", []))
    return sorted(caps_c & caps_d)


def domain_overlap(correct: dict, distractor: dict) -> dict:
    lob_c = set(correct.get("lineOfBusiness", []))
    lob_d = set(distractor.get("lineOfBusiness", []))
    et_c = set(correct.get("entityTypes", []))
    et_d = set(distractor.get("entityTypes", []))
    return {
        "shared_lob": sorted(lob_c & lob_d),
        "shared_entity_types": sorted(et_c & et_d),
    }
