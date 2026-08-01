"""Extended ambiguity metric — original structural metric + semantic fields.

This module does NOT replace the benchmark's ambiguity metric
(src/adversarial/preselect.py). It EXTENDS it, so the disambiguation
experiment can measure one thing: does adding the design-time semantic
fields to the similarity computation pull ambiguous resource pairs apart?

Original metric (preselect._pairwise_sim), six dimensions, all weight 1.0:
    text, localId, entityTypes, lineOfBusiness, tags, industry

Extended metric adds three semantic dimensions that only exist on
Enriched-ORD (written back by the design-time flow):
    capabilities   — Jaccard over verb-noun capability tokens
    partOfGroups   — Jaccard over business-process group IDs
    useCases       — TF-IDF cosine over the natural-language use-case text

The three additions are the same fields Methods A/C/D consume, so a drop in
pairwise ambiguity here is the structural counterpart of the retrieval lift
those methods show under enrichment.

Two callables are exposed:
    pairwise_original(a, b, ...)  — reproduces preselect exactly
    pairwise_extended(a, b, ...)  — original numerator/denominator + 3 fields

Both return (score, breakdown). A semantic dimension enters the extended score
only when BOTH resources carry the field, so any difference from the original
comes purely from the added fields, never from a larger denominator.
"""

from __future__ import annotations

import math

from src.adversarial import preselect


# The three semantic dimensions we add. Same unit weight as the originals so
# the extension does not privilege the new fields — it just gives them a vote.
SEMANTIC_WEIGHTS = {
    "capabilities": 1.0,
    "partOfGroups": 1.0,
    "useCases":     1.0,
}


# ── semantic field extraction ───────────────────────────────────────────────


def _group_ids(r: dict) -> set[str]:
    out: set[str] = set()
    for g in r.get("partOfGroups") or []:
        gid = g.get("groupId") if isinstance(g, dict) else g
        if gid:
            out.add(gid)
    return out


def _capabilities(r: dict) -> set[str]:
    return set(r.get("capabilities") or [])


def _usecase_text(r: dict) -> str:
    ucs = r.get("useCases") or []
    return " ".join(ucs) if ucs else ""


def build_usecase_tfidf(resources: list[dict]) -> dict[str, dict[str, float]]:
    """TF-IDF index over the useCases text, reusing preselect's tokeniser and
    the identical smoothed-IDF formula so the useCases dimension is scored the
    same way the original `text` dimension is."""
    N = len(resources)
    doc_tokens: dict[str, list[str]] = {}
    for r in resources:
        doc_tokens[r["ordId"]] = preselect._tokenize(_usecase_text(r))

    from collections import defaultdict
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


# ── the two scorers ──────────────────────────────────────────────────────────


def pairwise_original(a, b, et_idf, tfidf):
    """Thin passthrough to preselect so the baseline is provably identical."""
    return preselect._pairwise_sim(a, b, et_idf, tfidf)


def pairwise_extended(a, b, et_idf, tfidf, uc_tfidf):
    """Original six dimensions + capabilities/partOfGroups/useCases.

    A semantic dimension is added to BOTH numerator and denominator only when
    BOTH resources carry that field. If either side lacks it, the dimension is
    skipped entirely — the denominator stays 6 and the pair scores exactly as
    under the original metric. This removes the denominator artefact: a score
    can only drop because two resources that both describe capabilities /
    processes / use cases describe *different* ones, never merely because one
    side has metadata the other lacks.

    The six base dimensions keep the original fixed weighting, so the base part
    of the score is identical to pairwise_original.
    """
    # ── original six (recomputed via preselect helpers, verbatim) ──────────
    base_scores = {
        "text":           preselect._cosine_tfidf(tfidf.get(a["ordId"], {}),
                                                   tfidf.get(b["ordId"], {})),
        "localId":        preselect._jaccard(preselect._localid_tokens(a),
                                             preselect._localid_tokens(b)),
        "entityTypes":    preselect._et_sim_idf(a, b, et_idf),
        "lineOfBusiness": preselect._jaccard(set(a.get("lineOfBusiness") or []),
                                             set(b.get("lineOfBusiness") or [])),
        "tags":           preselect._jaccard(set(a.get("tags") or []),
                                             set(b.get("tags") or [])),
        "industry":       preselect._jaccard(set(a.get("industry") or []),
                                             set(b.get("industry") or [])),
    }

    # numerator/denominator start from the original six (fixed weight 1.0 each)
    numerator = sum(base_scores[f] * preselect.WEIGHTS[f] for f in preselect.WEIGHTS)
    denominator = len(preselect.WEIGHTS)

    # ── three semantic additions: counted only when BOTH sides have data ───
    caps_a, caps_b = _capabilities(a), _capabilities(b)
    grp_a, grp_b = _group_ids(a), _group_ids(b)
    uc_a = a.get("useCases") or []
    uc_b = b.get("useCases") or []

    sem_scores = {}
    if caps_a and caps_b:
        sem_scores["capabilities"] = preselect._jaccard(caps_a, caps_b)
    if grp_a and grp_b:
        sem_scores["partOfGroups"] = preselect._jaccard(grp_a, grp_b)
    if uc_a and uc_b:
        sem_scores["useCases"] = preselect._cosine_tfidf(uc_tfidf.get(a["ordId"], {}),
                                                         uc_tfidf.get(b["ordId"], {}))

    for f, v in sem_scores.items():
        numerator += v * SEMANTIC_WEIGHTS[f]
        denominator += SEMANTIC_WEIGHTS[f]

    cross_ns = a.get("namespace") != b.get("namespace")
    if cross_ns:
        numerator += preselect.CROSS_NAMESPACE_BONUS

    raw = numerator / denominator

    same_type = (a.get("_rtype") or a.get("type")) == (b.get("_rtype") or b.get("type"))
    total = raw if same_type else raw * preselect.TYPE_PENALTY

    breakdown = {k: round(v, 4) for k, v in base_scores.items()}
    # report semantic scores; None marks "dimension not active for this pair"
    breakdown["capabilities"] = round(sem_scores.get("capabilities"), 4) if "capabilities" in sem_scores else None
    breakdown["partOfGroups"] = round(sem_scores.get("partOfGroups"), 4) if "partOfGroups" in sem_scores else None
    breakdown["useCases"] = round(sem_scores.get("useCases"), 4) if "useCases" in sem_scores else None
    breakdown["n_semantic_dims_active"] = len(sem_scores)
    breakdown["same_type"] = same_type
    breakdown["cross_namespace"] = cross_ns

    return round(total, 4), breakdown
