"""Objective structural ambiguity scoring for ORD resources.

No LLM calls. Fully deterministic, reproducible.

Based exclusively on fields defined in the official ORD v1.16 specification.
No custom fields used.

Four orthogonal similarity signals per resource pair:

  1. type_match     — same ORD resource type (agent/apiResource/dataProduct/event)?
                      Different type → penalty ×0.5
  2. namespace_same — same system namespace?
                      Cross-namespace → bonus (models P1: agent sprawl)
  3. entityType_sim — IDF-weighted Jaccard over shared business objects
                      (relatedEntityTypes / exposedEntityTypes / entityTypes)
                      Rare entity types count more than common ones (IDF)
  4. text_sim       — TF-IDF cosine over title + shortDescription + description
                      Captures semantic overlap in human-authored descriptions

Additional structured signals (Jaccard, equal weight):
  5. lob_sim        — lineOfBusiness (ORD standard field for all resource types)
  6. tag_sim        — tags (ORD standard field for all resource types)
  7. industry_sim   — industry (ORD standard field for agent/apiResource/dataProduct)

All signals except type_match and cross-namespace carry equal weight (1.0).
EntityTypes use IDF weighting — the only justified deviation: rare entity types
are stronger disambiguation signals than common ones (same reasoning as TF-IDF
in information retrieval, mathematically well-established).

Type penalty and cross-namespace bonus are applied after normalization.
Normalizer = sum of weights for dimensions where BOTH resources have data,
so sparse fields do not penalize resources that legitimately lack them.
"""

from __future__ import annotations
import math
import re
from collections import defaultdict


# ── Weights (all 1.0 except IDF which is computed, not a weight) ─────────────

WEIGHTS = {
    "text":          1.0,   # TF-IDF cosine: title + shortDescription + description
    "localId":       1.0,   # Jaccard over camel-case-split tokens of localId
    "entityTypes":   1.0,   # IDF-weighted Jaccard over business object references
    "lineOfBusiness": 1.0,  # plain Jaccard
    "tags":          1.0,   # plain Jaccard
    "industry":      1.0,   # plain Jaccard
}

# Applied AFTER normalization when types differ
TYPE_PENALTY = 0.5

# Added as raw bonus to numerator (not normalized) when namespaces differ
CROSS_NAMESPACE_BONUS = 0.5

STOPWORDS = {
    "a", "an", "the", "for", "to", "of", "in", "is", "with", "and", "or",
    "at", "on", "by", "from", "be", "are", "has", "have", "do", "does",
    "their", "this", "that", "it", "its", "as", "after", "before", "when",
    "where", "how", "what", "who", "all", "any", "each", "per", "new",
    "get", "set", "run", "use", "add", "into", "out", "up", "not", "no",
    "if", "else", "then", "than", "so", "but", "also", "more", "than",
    "been", "was", "were", "will", "can", "may", "should", "would",
}

DIFFICULTY_BANDS = [
    ("easy",      0.0,  0.20),
    ("medium",    0.20, 0.40),
    ("hard",      0.40, 0.60),
    ("very_hard", 0.60, 1.01),
]

TOP_K = 5
COVERAGE_GAP_THRESHOLD = 0.25
GROUND_TRUTH_TYPES = {"agent", "apiResource", "dataProduct"}


# ── Entity type normalization ─────────────────────────────────────────────────


def _extract_entity_types(r: dict) -> list[str]:
    """Normalize entity type references across all ORD resource types.

    ORD v1.16 uses different field names and structures per type:
      agent            → relatedEntityTypes  (string[])
      apiResource      → exposedEntityTypes  ([{ordId}])
      dataProduct      → entityTypes         (string[])
      eventResource    → exposedEntityTypes  ([{ordId}])
    """
    out: list[str] = []
    seen: set[str] = set()

    def _add(v: str) -> None:
        if v and v not in seen:
            out.append(v)
            seen.add(v)

    for ref in r.get("relatedEntityTypes") or []:
        if isinstance(ref, str):
            _add(ref)
        elif isinstance(ref, dict) and ref.get("ordId"):
            _add(ref["ordId"])

    for ref in r.get("exposedEntityTypes") or []:
        if isinstance(ref, str):
            _add(ref)
        elif isinstance(ref, dict) and ref.get("ordId"):
            _add(ref["ordId"])

    for ref in r.get("entityTypes") or []:
        if isinstance(ref, str):
            _add(ref)
        elif isinstance(ref, dict) and ref.get("ordId"):
            _add(ref["ordId"])

    return out


# ── Text processing ───────────────────────────────────────────────────────────


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric, remove stopwords."""
    tokens = re.split(r"[^a-zA-Z0-9]+", text.lower())
    return [t for t in tokens if len(t) > 2 and t not in STOPWORDS]


def _localid_tokens(r: dict) -> set[str]:
    """Extract tokens from the localId (or ordId component) via CamelCase split.

    e.g. 'RecruiterAssistant' → {'recruiter', 'assistant'}
         'CustomerOrder'      → {'customer', 'order'}

    Falls back to the third segment of ordId if localId is absent.
    """
    raw = r.get("localId") or (r.get("ordId", "").split(":")[2] if r.get("ordId") else "")
    # Split CamelCase: insert space before each uppercase letter
    spaced = re.sub(r"([A-Z])", r" \1", raw).strip()
    tokens = re.split(r"[^a-zA-Z0-9]+", spaced.lower())
    return {t for t in tokens if len(t) > 2 and t not in STOPWORDS}


def _resource_text(r: dict) -> str:
    """Concatenate title + shortDescription + description for TF-IDF."""
    parts = [
        r.get("title", ""),
        r.get("shortDescription", ""),
        r.get("description", ""),
    ]
    return " ".join(p for p in parts if p)


def _build_tfidf_index(resources: list[dict]) -> dict[str, dict[str, float]]:
    """Build TF-IDF vectors over title+shortDescription+description.

    TF = term frequency within resource text (normalized by doc length).
    IDF = log((N+1)/(df+1)) — smoothed to avoid zero division.
    """
    N = len(resources)
    doc_tokens: dict[str, list[str]] = {}
    for r in resources:
        doc_tokens[r["ordId"]] = _tokenize(_resource_text(r))

    df: dict[str, int] = defaultdict(int)
    for tokens in doc_tokens.values():
        for term in set(tokens):
            df[term] += 1

    tfidf: dict[str, dict[str, float]] = {}
    for r in resources:
        oid = r["ordId"]
        tokens = doc_tokens[oid]
        if not tokens:
            tfidf[oid] = {}
            continue
        tf: dict[str, float] = defaultdict(float)
        for t in tokens:
            tf[t] += 1.0
        doc_len = len(tokens)
        tfidf[oid] = {
            term: (count / doc_len) * math.log((N + 1) / (df[term] + 1))
            for term, count in tf.items()
        }
    return tfidf


def _cosine_tfidf(va: dict[str, float], vb: dict[str, float]) -> float:
    if not va or not vb:
        return 0.0
    shared = set(va) & set(vb)
    dot = sum(va[t] * vb[t] for t in shared)
    norm_a = math.sqrt(sum(v * v for v in va.values()))
    norm_b = math.sqrt(sum(v * v for v in vb.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Entity type IDF ───────────────────────────────────────────────────────────


def _et_idf(resources: list[dict]) -> dict[str, float]:
    """IDF weight per entityType ordId.

    Rare entity types (few resources reference them) get high weight.
    Common ones (many resources share them) get low weight.
    Formula: 1 / log(1 + count) — soft inverse, no extreme values.
    """
    counts: dict[str, int] = defaultdict(int)
    for r in resources:
        for et in _extract_entity_types(r):
            counts[et] += 1
    return {et: 1.0 / math.log(1 + cnt) for et, cnt in counts.items()}


def _et_sim_idf(a: dict, b: dict, idf: dict[str, float]) -> float:
    """IDF-weighted Jaccard over entity type references."""
    ets_a = set(_extract_entity_types(a))
    ets_b = set(_extract_entity_types(b))
    if not ets_a and not ets_b:
        return 0.0
    shared = ets_a & ets_b
    union = ets_a | ets_b
    num = sum(idf.get(et, 0.0) for et in shared)
    den = sum(idf.get(et, 0.0) for et in union)
    return num / den if den > 0 else 0.0


# ── Jaccard helpers ───────────────────────────────────────────────────────────


def _jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union > 0 else 0.0


# ── Pairwise similarity ───────────────────────────────────────────────────────


def _pairwise_sim(
    a: dict,
    b: dict,
    et_idf: dict[str, float],
    tfidf: dict[str, dict[str, float]],
) -> tuple[float, dict]:
    """Compute similarity between two ORD resources.

    Returns (final_score, breakdown_dict).

    Breakdown fields:
      text           — TF-IDF cosine over title+shortDescription+description
      localId        — Jaccard over CamelCase-split tokens of localId / ordId component
      entityTypes    — IDF-Jaccard over business object references
      lineOfBusiness — plain Jaccard
      tags           — plain Jaccard
      industry       — plain Jaccard
      same_type      — bool: do they share the same ORD resource type?
      cross_namespace— bool: are they from different system namespaces?
      type_penalty_applied — bool
      cross_namespace_bonus_applied — bool
    """
    lid_a = _localid_tokens(a)
    lid_b = _localid_tokens(b)
    lob_a = set(a.get("lineOfBusiness") or [])
    lob_b = set(b.get("lineOfBusiness") or [])
    tags_a = set(a.get("tags") or [])
    tags_b = set(b.get("tags") or [])
    ind_a = set(a.get("industry") or [])
    ind_b = set(b.get("industry") or [])
    ets_a = set(_extract_entity_types(a))
    ets_b = set(_extract_entity_types(b))
    va = tfidf.get(a["ordId"], {})
    vb = tfidf.get(b["ordId"], {})

    scores: dict[str, float] = {
        "text":           _cosine_tfidf(va, vb) if va or vb else 0.0,
        "localId":        _jaccard(lid_a, lid_b),
        "entityTypes":    _et_sim_idf(a, b, et_idf) if ets_a or ets_b else 0.0,
        "lineOfBusiness": _jaccard(lob_a, lob_b),
        "tags":           _jaccard(tags_a, tags_b),
        "industry":       _jaccard(ind_a, ind_b),
    }

    # Equal weights: sum / N_DIMENSIONS, then cross-namespace bonus, then type penalty
    N_DIMENSIONS = len(WEIGHTS)
    numerator = sum(scores[f] * WEIGHTS[f] for f in WEIGHTS)

    # Cross-namespace bonus (raw, not normalized — models P1 regardless of other sims)
    cross_ns = a.get("namespace") != b.get("namespace")
    if cross_ns:
        numerator += CROSS_NAMESPACE_BONUS

    raw = numerator / N_DIMENSIONS

    # Type penalty after normalization
    same_type = (a.get("_rtype") or a.get("type")) == (b.get("_rtype") or b.get("type"))
    total = raw if same_type else raw * TYPE_PENALTY

    breakdown = {
        k: round(v, 4) for k, v in scores.items()
    }
    breakdown["same_type"] = same_type
    breakdown["cross_namespace"] = cross_ns
    breakdown["type_penalty_applied"] = not same_type
    breakdown["cross_namespace_bonus_applied"] = cross_ns

    return round(total, 4), breakdown


# ── Utility ───────────────────────────────────────────────────────────────────


def _difficulty_band(score: float) -> str:
    for name, lo, hi in DIFFICULTY_BANDS:
        if lo <= score < hi:
            return name
    return "very_hard"


def _problem_labels(breakdown: dict) -> list[str]:
    problems = []
    if breakdown.get("cross_namespace"):
        problems.append("P1")
    if (breakdown.get("entityTypes") or 0) > 0 or (breakdown.get("tags") or 0) > 0:
        problems.append("P2")
    if (breakdown.get("text") or 0) < 0.2 and (breakdown.get("entityTypes") or 0) > 0:
        problems.append("P3")
    return sorted(set(problems)) or ["P2"]


# ── Public API ────────────────────────────────────────────────────────────────


def compute_landscape_ambiguity(
    resources: list[dict],
    top_k: int = TOP_K,
    exclude_types: set[str] | None = None,
) -> dict:
    """Compute ambiguity scores for all retrieval resources.

    Every resource gets a score = mean(sim to top-k neighbors).
    All 176 pairwise scores are stored in all_neighbors for full auditability.
    """
    exclude_types = exclude_types or {"entityType"}
    scored = [r for r in resources if (r.get("_rtype") or r.get("type")) not in exclude_types]

    idf = _et_idf(scored)
    tfidf = _build_tfidf_index(scored)

    per_resource: list[dict] = []

    for i, r in enumerate(scored):
        neighbors = []
        for j, other in enumerate(scored):
            if i == j:
                continue
            sim, breakdown = _pairwise_sim(r, other, idf, tfidf)
            neighbors.append({
                "ordId":     other["ordId"],
                "title":     other.get("title", ""),
                "type":      other.get("type", ""),
                "namespace": other.get("namespace", ""),
                "sim":       sim,
                "breakdown": breakdown,
                "problems":  _problem_labels(breakdown),
            })

        neighbors.sort(key=lambda x: -x["sim"])
        top_neighbors = neighbors[:top_k]
        above = [nb for nb in neighbors if nb["sim"] >= COVERAGE_GAP_THRESHOLD]

        amb_score = (
            sum(nb["sim"] for nb in top_neighbors) / len(top_neighbors)
            if top_neighbors else 0.0
        )

        per_resource.append({
            "ordId":                      r["ordId"],
            "title":                      r.get("title", ""),
            "type":                       r.get("type", ""),
            "namespace":                  r.get("namespace", ""),
            "ambiguity_score":            round(amb_score, 4),
            "difficulty_band":            _difficulty_band(amb_score),
            "top_neighbors":              top_neighbors,
            "all_neighbors":              neighbors,
            "n_neighbors_above_threshold": len(above),
            "coverage_gap":               len(above) == 0,
            "can_be_ground_truth":        (r.get("_rtype") or r.get("type")) in GROUND_TRUTH_TYPES,
        })

    # Summary
    bands: dict[str, int] = defaultdict(int)
    gaps = 0
    by_ns: dict[str, list[float]] = defaultdict(list)
    for rr in per_resource:
        bands[rr["difficulty_band"]] += 1
        if rr["coverage_gap"]:
            gaps += 1
        by_ns[rr["namespace"]].append(rr["ambiguity_score"])

    by_namespace = {
        ns: {
            "mean_ambiguity": round(sum(sc) / len(sc), 4),
            "n_resources":    len(sc),
            "n_hard":         sum(1 for s in sc if s >= 0.40),
            "n_gaps":         sum(
                1 for rr in per_resource
                if rr["namespace"] == ns and rr["coverage_gap"]
            ),
        }
        for ns, sc in sorted(by_ns.items())
    }

    seen: set[tuple[str, str]] = set()
    all_pairs: list[dict] = []
    for rr in per_resource:
        for nb in rr["top_neighbors"]:
            key = tuple(sorted([rr["ordId"], nb["ordId"]]))
            if key not in seen and nb["sim"] >= COVERAGE_GAP_THRESHOLD:
                seen.add(key)
                all_pairs.append({
                    "ordId_A":   rr["ordId"],
                    "ordId_B":   nb["ordId"],
                    "sim":       nb["sim"],
                    "breakdown": nb["breakdown"],
                    "problems":  nb["problems"],
                })
    all_pairs.sort(key=lambda x: -x["sim"])

    return {
        "summary": {
            "total_resources":        len(per_resource),
            "easy":                   bands["easy"],
            "medium":                 bands["medium"],
            "hard":                   bands["hard"],
            "very_hard":              bands["very_hard"],
            "coverage_gaps":          gaps,
            "weights_used":           WEIGHTS,
            "type_penalty":           TYPE_PENALTY,
            "cross_namespace_bonus":  CROSS_NAMESPACE_BONUS,
            "coverage_gap_threshold": COVERAGE_GAP_THRESHOLD,
            "top_k":                  top_k,
        },
        "by_namespace":        by_namespace,
        "top_ambiguous_pairs": all_pairs[:20],
        "resources":           per_resource,
    }


def pre_select_ambiguous_pairs(
    resources: list[dict],
    top_k_pairs: int = 50,
    min_score: float = COVERAGE_GAP_THRESHOLD,
    ground_truth_types: set[str] | None = None,
) -> list[dict]:
    """Return top-k most ambiguous (correct, distractor) pairs."""
    ground_truth_types = ground_truth_types or GROUND_TRUTH_TYPES
    report = compute_landscape_ambiguity(resources)
    pairs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rr in report["resources"]:
        if (rr.get("_rtype") or rr["type"]) not in ground_truth_types:
            continue
        for nb in rr["top_neighbors"]:
            if nb["sim"] < min_score:
                continue
            key = (rr["ordId"], nb["ordId"])
            if key in seen:
                continue
            seen.add(key)
            pairs.append({
                "correct_ordId":         rr["ordId"],
                "distractor_ordId":      nb["ordId"],
                "overlap_score":         nb["sim"],
                "overlap_breakdown":     nb["breakdown"],
                "problems":              nb["problems"],
                "correct_difficulty_band": rr["difficulty_band"],
            })
    pairs.sort(key=lambda x: -x["overlap_score"])
    return pairs[:top_k_pairs]
