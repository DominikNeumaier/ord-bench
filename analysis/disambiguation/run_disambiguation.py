"""Disambiguation experiment — does the design-time semantic layer reduce
structural ambiguity between ORD resources?

The benchmark's ambiguity metric (src/adversarial/preselect.py) scores
resource similarity on six fields, none of them semantic. This experiment
extends that metric with the three design-time fields (capabilities,
partOfGroups, useCases) and measures whether ambiguous pairs move apart.

Three analyses, all writing to analysis/disambiguation/output/:

  1. Per-resource ambiguity, original vs extended metric.
     For every ground-truth-eligible resource: mean similarity to its top-k
     neighbours under each metric. Paired delta = disambiguation effect.
     CAVEAT: the extended metric divides by 9 dimensions instead of 6, so a
     lower score is partly a denominator effect. Analysis 2 removes that.

  2. Denominator-free check on hard pairs.
     For the pairs the ORIGINAL metric ranks as most ambiguous, compute their
     semantic-only similarity (the three added fields alone). If hard pairs
     have low semantic similarity, the semantic layer separates exactly the
     pairs that text/entityTypes conflate. No denominator confound.

  3. Embedding counter-check (no API — reads the on-disk cache only).
     For each resource, embedding cosine to its nearest neighbour using the
     clean Method-A text (title+shortDescription+description) vs the enriched
     text (+ semantic fields). Does the enriched embedding pull neighbours
     apart? Reports cache coverage; skips misses.

Run:  python analysis/disambiguation/run_disambiguation.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "src").is_dir())
sys.path.insert(0, str(ROOT))

from src import config, loader as ord_loader          # noqa: E402
from src.adversarial import preselect            # noqa: E402
from analysis.disambiguation import extended_metric as em  # noqa: E402

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)

TOP_K = preselect.TOP_K            # 5, same as the benchmark
GT_TYPES = preselect.GROUND_TRUTH_TYPES

# Same similarity tiers the benchmark uses to certify difficulty
# (src/generation/enrich_landscape.py). A HIGH-tier neighbour
# (sim >= 0.50) is a genuine confusable — the exact quantity Fig. 4 tracks.
HIGH_THRESHOLD = 0.50
MEDIUM_THRESHOLD = 0.25


# ── embedding cache access (identical hashing to src/core/llm.embed) ─────────


def _hash(payload) -> str:
    s = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(s.encode()).hexdigest()


def _cached_embedding(text: str) -> np.ndarray | None:
    key = _hash({"model": config.EMBEDDING_MODEL, "text": text})
    # Embeddings ship with the repo under analysis/embedding_analysis/embed_cache/;
    # fall back to the global cache/embed/ for any key not in the bundled set.
    cp = ROOT / "analysis" / "embedding_analysis" / "embed_cache" / f"{key}.json"
    if not cp.exists():
        cp = config.CACHE_DIR / "embed" / f"{key}.json"
    if not cp.exists():
        return None
    return np.asarray(json.loads(cp.read_text())["vec"], dtype=np.float64)


def _clean_text(r: dict) -> str:
    parts = [r.get("title", ""), r.get("shortDescription", ""), r.get("description", "")]
    return " | ".join(p for p in parts if p)


def _enriched_text(r: dict) -> str:
    """Method A's _resource_text, inlined to avoid importing the openai client.

    This is the full retriever-facing text (all four semantic fields incl.
    processNext) and is used by the nearest-neighbour analysis, which models
    what a real embedding retriever ingests.
    """
    parts = [r["title"], r["shortDescription"], r["description"]]
    groups = r.get("partOfGroups") or []
    if groups:
        names = [g.get("groupId", "") for g in groups]
        parts.append("partOfGroups: " + ", ".join(n for n in names if n))
    nexts = r.get("processNext") or []
    if nexts:
        parts.append("processNext: " + ", ".join(nexts))
    caps = r.get("capabilities") or []
    if caps:
        parts.append("capabilities: " + ", ".join(caps))
    ucs = r.get("useCases") or []
    if ucs:
        parts.append("useCases: " + " | ".join(ucs))
    return " | ".join(p for p in parts if p)


def _enriched_text_semantic(r: dict) -> str:
    """Enriched text for the field-symmetric clean-vs-enriched comparison.

    Identical to _enriched_text but WITHOUT processNext. processNext is a
    process-sequence relation, not a similarity dimension: two resources that
    share a next step are adjacent in a workflow, not interchangeable. The
    structural extended metric adds exactly the three semantic similarity
    dimensions (capabilities, partOfGroups, useCases) and deliberately excludes
    processNext for the same reason. Mirroring that exclusion on the embedding
    side keeps both measures over identical fields, so the opposite-direction
    result cannot be an artefact of a field mismatch.
    """
    parts = [r["title"], r["shortDescription"], r["description"]]
    groups = r.get("partOfGroups") or []
    if groups:
        names = [g.get("groupId", "") for g in groups]
        parts.append("partOfGroups: " + ", ".join(n for n in names if n))
    caps = r.get("capabilities") or []
    if caps:
        parts.append("capabilities: " + ", ".join(caps))
    ucs = r.get("useCases") or []
    if ucs:
        parts.append("useCases: " + " | ".join(ucs))
    return " | ".join(p for p in parts if p)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(a @ b / (na * nb))


# ── analysis 1 + 2: structural ─────────────────────────────────────────────


def _is_enriched(r: dict) -> bool:
    """A resource carries semantic content only if the design-time flow wrote
    at least one of the three fields."""
    return bool(r.get("capabilities") or r.get("partOfGroups") or r.get("useCases"))


def structural_analysis(resources: list[dict], population: str = "enriched") -> dict:
    """Count HIGH-tier neighbours per resource under the original metric vs the
    extended metric, using the same tier (sim >= 0.50) the benchmark certifies
    with and Fig. 4 reports.

    population:
      "all"      — every retrieval resource (273). Consistent with Fig. 4, which
                   averages over the whole landscape. For the 203 non-enriched
                   resources the extended metric equals the original (active-
                   dimension normalisation skips absent fields), so their delta
                   is 0 and the landscape-wide effect is diluted but honest.
      "enriched" — only the GT-eligible resources that carry enrichment (70).
                   Isolates the effect where the added fields can act at all.
      "enriched_pairs" — same 70 target resources, but the neighbour pool is
                   restricted to OTHER enriched resources, so every counted pair
                   is one where the metric can actually act on both sides. This
                   is the cleanest view of the disambiguation effect.

    In the "all"/"enriched" cases the neighbour pool is the FULL landscape (a
    resource's distractors can be any other resource); "enriched_pairs" narrows
    the neighbour pool to enriched resources only.
    """
    scored = [r for r in resources if (r.get("_rtype") or r.get("type")) != "entityType"]
    et_idf = preselect._et_idf(scored)
    tfidf = preselect._build_tfidf_index(scored)
    uc_tfidf = em.build_usecase_tfidf(scored)

    neighbours_enriched_only = False
    if population == "all":
        targets = scored
    elif population == "enriched":
        targets = [r for r in scored
                   if (r.get("_rtype") or r.get("type")) in GT_TYPES and _is_enriched(r)]
    elif population == "enriched_pairs":
        targets = [r for r in scored
                   if (r.get("_rtype") or r.get("type")) in GT_TYPES and _is_enriched(r)]
        neighbours_enriched_only = True
    else:
        raise ValueError(f"unknown population {population!r}")

    per_resource = []
    hard_pairs = []          # hardest ORIGINAL neighbour + its extended score

    for r in targets:
        orig_sims, ext_sims = [], []
        top_orig_pair = None
        for other in scored:
            if r["ordId"] == other["ordId"]:
                continue
            if neighbours_enriched_only and not _is_enriched(other):
                continue
            so, _ = em.pairwise_original(r, other, et_idf, tfidf)
            se, bd = em.pairwise_extended(r, other, et_idf, tfidf, uc_tfidf)
            orig_sims.append(so)
            ext_sims.append((se, other["ordId"], bd))
            if top_orig_pair is None or so > top_orig_pair[0]:
                top_orig_pair = (so, se, other["ordId"], bd)

        # a target with no eligible neighbour (only in enriched_pairs) is skipped
        if not orig_sims:
            continue

        n_high_orig = sum(1 for s in orig_sims if s >= HIGH_THRESHOLD)
        n_med_orig = sum(1 for s in orig_sims if MEDIUM_THRESHOLD <= s < HIGH_THRESHOLD)
        ext_only = [s for s, _, _ in ext_sims]
        n_high_ext = sum(1 for s in ext_only if s >= HIGH_THRESHOLD)
        n_med_ext = sum(1 for s in ext_only if MEDIUM_THRESHOLD <= s < HIGH_THRESHOLD)

        # In enriched_pairs mode we average only over targets that actually have
        # an enriched HIGH neighbour — the resources where the effect can be
        # observed at all. Targets with zero enriched HIGH neighbours are skipped
        # so they do not dilute the average with structural zeros.
        if neighbours_enriched_only and n_high_orig == 0:
            continue

        per_resource.append({
            "ordId": r["ordId"],
            "type": r.get("type", ""),
            "namespace": r.get("namespace", ""),
            "n_high_original": n_high_orig,
            "n_high_extended": n_high_ext,
            "n_high_delta": n_high_ext - n_high_orig,
            "n_medium_original": n_med_orig,
            "n_medium_extended": n_med_ext,
        })

        # hardest original neighbour: does the extension push it below HIGH?
        base_sim, ext_sim, dist_id, bd = top_orig_pair
        hard_pairs.append({
            "correct": r["ordId"],
            "distractor": dist_id,
            "sim_original": round(base_sim, 4),
            "sim_extended": round(ext_sim, 4),
            "cap_sim": bd.get("capabilities"),
            "group_sim": bd.get("partOfGroups"),
            "usecase_sim": bd.get("useCases"),
            "n_semantic_dims_active": bd.get("n_semantic_dims_active", 0),
            "dropped_below_high": base_sim >= HIGH_THRESHOLD and ext_sim < HIGH_THRESHOLD,
        })

    tot_high_orig = sum(p["n_high_original"] for p in per_resource)
    tot_high_ext = sum(p["n_high_extended"] for p in per_resource)
    n = len(per_resource)
    hard_high = [hp for hp in hard_pairs if hp["sim_original"] >= HIGH_THRESHOLD]
    dropped = [hp for hp in hard_high if hp["dropped_below_high"]]

    return {
        "per_resource": per_resource,
        "hard_pairs": sorted(hard_pairs, key=lambda x: -x["sim_original"]),
        "summary": {
            "population": population,
            "n_resources": n,
            "avg_high_neighbors_original": round(tot_high_orig / n, 3) if n else 0.0,
            "avg_high_neighbors_extended": round(tot_high_ext / n, 3) if n else 0.0,
            "total_high_pairs_original": tot_high_orig,
            "total_high_pairs_extended": tot_high_ext,
            "high_pairs_removed": tot_high_orig - tot_high_ext,
            "high_pairs_removed_pct": round(100 * (tot_high_orig - tot_high_ext) / tot_high_orig, 1) if tot_high_orig else 0.0,
            "n_resources_with_fewer_high": sum(1 for p in per_resource if p["n_high_delta"] < 0),
            "n_resources_with_more_high": sum(1 for p in per_resource if p["n_high_delta"] > 0),
            "pct_resources_with_fewer_high": round(100 * sum(1 for p in per_resource if p["n_high_delta"] < 0) / n, 1) if n else 0.0,
            # hardest-neighbour view
            "hardest_neighbour_high_n": len(hard_high),
            "hardest_neighbour_dropped_below_high": len(dropped),
            "hardest_neighbour_dropped_pct": round(100 * len(dropped) / len(hard_high), 1) if hard_high else 0.0,
        },
    }


# ── analysis 3: embedding counter-check ─────────────────────────────────────


def embedding_analysis(clean_res: list[dict], enriched_res: list[dict]) -> dict:
    enriched_by_id = {r["ordId"]: r for r in enriched_res}
    # same population as the structural analysis: GT-eligible AND enriched,
    # so both figures describe the identical resource set.
    gt = [r for r in clean_res
          if (r.get("_rtype") or r.get("type")) in GT_TYPES
          and r["ordId"] in enriched_by_id
          and _is_enriched(enriched_by_id[r["ordId"]])]

    # pull both embedding sets from cache
    clean_vecs, enr_vecs, ids = {}, {}, []
    misses_clean = misses_enr = 0
    for r in gt:
        oid = r["ordId"]
        cv = _cached_embedding(_clean_text(r))
        ev = _cached_embedding(_enriched_text(enriched_by_id[oid]))
        if cv is None:
            misses_clean += 1
        if ev is None:
            misses_enr += 1
        if cv is None or ev is None:
            continue
        clean_vecs[oid] = cv
        enr_vecs[oid] = ev
        ids.append(oid)

    rows = []
    for oid in ids:
        # nearest neighbour cosine under each representation, over the covered set
        best_clean = max((_cosine(clean_vecs[oid], clean_vecs[o]) for o in ids if o != oid), default=0.0)
        best_enr = max((_cosine(enr_vecs[oid], enr_vecs[o]) for o in ids if o != oid), default=0.0)
        rows.append({
            "ordId": oid,
            "nn_cosine_clean": round(best_clean, 4),
            "nn_cosine_enriched": round(best_enr, 4),
            "delta": round(best_enr - best_clean, 4),
        })

    deltas = [r["delta"] for r in rows]
    return {
        "coverage": {
            "gt_resources": len(gt),
            "covered": len(ids),
            "misses_clean_text": misses_clean,
            "misses_enriched_text": misses_enr,
        },
        "per_resource": rows,
        "summary": {
            "mean_nn_cosine_clean": round(np.mean([r["nn_cosine_clean"] for r in rows]), 4) if rows else None,
            "mean_nn_cosine_enriched": round(np.mean([r["nn_cosine_enriched"] for r in rows]), 4) if rows else None,
            "mean_delta": round(np.mean(deltas), 4) if rows else None,
            "pct_pulled_apart": round(100 * sum(1 for d in deltas if d < 0) / len(deltas), 1) if rows else None,
        } if rows else {"note": "no embedding cache coverage — run Method A first"},
    }


def avg_similarity_analysis(clean_res, enriched_res) -> dict:
    """Average pairwise ambiguity across ALL pairs of two enriched resources,
    under the structural metric and under embedding cosine, on identical pairs.

    Population: every unordered pair (a, b) where both resources carry all
    semantic fields (enriched). No HIGH filter — this reports the mean ambiguity
    over the whole enriched sub-landscape, so it answers "does enrichment lower
    the average ambiguity between fully-described resources?".

    Two metrics on the same pairs:
      structural — preselect._pairwise_sim (original 6 fields) vs
                   em.pairwise_extended (+ capabilities/partOfGroups/useCases)
      embedding  — cosine of Method-A text embeddings, clean text vs enriched text

    Restricting to enriched-only pairs is deliberate: for a mixed pair the
    structural metric leaves the denominator at 6 and reports zero change by
    construction, whereas the embedding still drifts, so a mixed-pair comparison
    would be unfair. Both metrics are therefore evaluated on the same enriched
    pairs.
    """
    clean_by_id = {r["ordId"]: r for r in clean_res}
    scored = [r for r in enriched_res if (r.get("_rtype") or r.get("type")) != "entityType"]
    et_idf = preselect._et_idf(scored)
    tfidf = preselect._build_tfidf_index(scored)
    uc_tfidf = em.build_usecase_tfidf(scored)
    enriched = [r for r in scored if _is_enriched(r)]

    struct_o, struct_e = [], []
    cos_c, cos_e = [], []
    # subset: pairs that were HIGH (>= 0.50) under the ORIGINAL structural metric
    hi_struct_o, hi_struct_e = [], []
    hi_cos_c, hi_cos_e = [], []
    n_pairs = 0
    emb_covered = 0
    for i, a in enumerate(enriched):
        for b in enriched[i + 1:]:
            n_pairs += 1
            so = preselect._pairwise_sim(a, b, et_idf, tfidf)[0]
            se = em.pairwise_extended(a, b, et_idf, tfidf, uc_tfidf)[0]
            struct_o.append(so)
            struct_e.append(se)
            ca = _cached_embedding(_clean_text(clean_by_id[a["ordId"]]))
            cb = _cached_embedding(_clean_text(clean_by_id[b["ordId"]]))
            ea = _cached_embedding(_enriched_text_semantic(a))
            eb = _cached_embedding(_enriched_text_semantic(b))
            has_emb = ca is not None and cb is not None and ea is not None and eb is not None
            if has_emb:
                emb_covered += 1
                cc, ce = _cosine(ca, cb), _cosine(ea, eb)
                cos_c.append(cc)
                cos_e.append(ce)
            if so >= HIGH_THRESHOLD:
                hi_struct_o.append(so)
                hi_struct_e.append(se)
                if has_emb:
                    hi_cos_c.append(cc)
                    hi_cos_e.append(ce)

    # ── mixed pairs (enriched x non-enriched): embedding only ──────────────
    # The structural metric reports no change here by construction (the semantic
    # dimensions need both sides), so only the embedding is meaningful. Even so,
    # enriching just ONE side shifts its vector and changes the cosine.
    non_enriched = [r for r in scored if not _is_enriched(r)]
    mix_cos_c, mix_cos_e = [], []
    for a in enriched:
        ea = _cached_embedding(_enriched_text_semantic(a))
        ca = _cached_embedding(_clean_text(clean_by_id[a["ordId"]]))
        if ea is None or ca is None:
            continue
        for b in non_enriched:
            # b has no semantic fields, so its text is identical in both states
            bt = _cached_embedding(_clean_text(clean_by_id[b["ordId"]]))
            if bt is None:
                continue
            mix_cos_c.append(_cosine(ca, bt))
            mix_cos_e.append(_cosine(ea, bt))

    def _stats(orig, ext):
        if not orig:
            return None
        mo, me = float(np.mean(orig)), float(np.mean(ext))
        return {
            "n": len(orig),
            "mean_original": round(mo, 4),
            "mean_extended": round(me, 4),
            "mean_delta": round(me - mo, 4),
            "pct_change": round(100 * (me - mo) / mo, 1) if mo else None,
            "pairs_less_similar": sum(1 for x, y in zip(orig, ext) if y < x),
            "pairs_more_similar": sum(1 for x, y in zip(orig, ext) if y > x),
        }

    return {
        "n_enriched_resources": len(enriched),
        "n_pairs": n_pairs,
        "embedding_covered": emb_covered,
        "structural": _stats(struct_o, struct_e),
        "embedding": _stats(cos_c, cos_e),
        "structural_high_subset": _stats(hi_struct_o, hi_struct_e),
        "embedding_mixed_pairs": _stats(mix_cos_c, mix_cos_e),
        "embedding_high_subset": _stats(hi_cos_c, hi_cos_e),
    }


def main():
    print("Loading landscapes …")
    clean = ord_loader.load_landscape(state="clean")
    enriched = ord_loader.load_landscape(state="enriched")
    print(f"  clean: {len(clean)}  enriched: {len(enriched)}")

    print("Structural analysis — all 273 resources (consistent with Fig. 4) …")
    struct_all = structural_analysis(enriched, population="all")
    print(json.dumps(struct_all["summary"], indent=2))

    print("Structural analysis — 70 enriched GT resources …")
    struct_enriched = structural_analysis(enriched, population="enriched")
    print(json.dumps(struct_enriched["summary"], indent=2))

    print("Structural analysis — enriched GT, enriched neighbours only …")
    struct_pairs = structural_analysis(enriched, population="enriched_pairs")
    print(json.dumps(struct_pairs["summary"], indent=2))

    print("Embedding counter-check (cache only, no API) …")
    embed = embedding_analysis(clean, enriched)
    print(json.dumps({**embed["coverage"], **embed["summary"]}, indent=2))

    print("Avg similarity on enriched pairs — structural vs embedding …")
    avg_sim = avg_similarity_analysis(clean, enriched)
    print(json.dumps(avg_sim, indent=2))

    result = {
        "structural_all": struct_all,
        "structural_enriched": struct_enriched,
        "structural_enriched_pairs": struct_pairs,
        "embedding_nn": embed,
        "avg_similarity_enriched_pairs": avg_sim,
    }
    (OUT / "disambiguation_report.json").write_text(json.dumps(result, indent=2))
    print(f"\nWrote {OUT / 'disambiguation_report.json'}")


if __name__ == "__main__":
    main()
