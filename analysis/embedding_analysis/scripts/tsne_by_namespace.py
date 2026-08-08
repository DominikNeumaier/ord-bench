#!/usr/bin/env python3
"""
Exploratory analysis: do resources of the same SYSTEM (namespace) cluster
together in embedding space, or are they intermixed across systems?

This complements the existing PCA figure. PCA captures only global linear
variance (~16%); t-SNE preserves LOCAL neighbourhood structure, which is what
"tools of one system are similar and form a group" actually means.

We answer the question two ways:
  1. QUANTITATIVE (full 3072-dim space, no projection distortion):
       - mean within-namespace vs. between-namespace cosine similarity
       - silhouette score with namespace as label (cosine metric)
  2. VISUAL (t-SNE 2D):
       - scatter coloured by namespace, with a large centroid marker per system
       - scatter coloured by resource type, with a centroid marker per type

Embeddings are pulled from the on-disk cache (no API calls), keyed by the same
hash llm.embed uses. Set EMBED_CACHE to override the cache location.

Run:
  ORD_STATE=enriched \
  EMBED_CACHE="/path/to/cache/embed" \
  python3 analysis/embedding_analysis/scripts/tsne_by_namespace.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

# repo root = three levels up from this script (scripts/ -> embedding_analysis/ -> paper1/ -> experiments/ -> ROOT)
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src import config, loader as ord_loader  # noqa: E402

OUT = ROOT / "analysis" / "embedding_analysis"
CACHE = Path(os.environ.get("EMBED_CACHE", str(Path(__file__).resolve().parent.parent / "embed_cache")))
STATE = os.environ.get("ORD_STATE", "enriched")
SEED = 42


# ── resource text (kept in sync with embedding_vs_metric.py) ────────────────
def resource_text(r: dict) -> str:
    parts = [r["title"], r["shortDescription"], r["description"]]
    groups = r.get("partOfGroups") or []
    if groups:
        parts.append("partOfGroups: " + ", ".join(g.get("groupId", "") for g in groups if g.get("groupId")))
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


def _key(text: str) -> str:
    s = json.dumps({"model": config.EMBEDDING_MODEL, "text": text}, sort_keys=True, default=str)
    return hashlib.sha256(s.encode()).hexdigest()


def cached_embedding(text: str) -> np.ndarray | None:
    cp = CACHE / f"{_key(text)}.json"
    if not cp.exists():
        return None
    return np.asarray(json.loads(cp.read_text())["vec"], dtype=np.float64)


def load():
    resources = ord_loader.load_landscape(state=STATE)
    resources = [r for r in resources if (r.get("_rtype") or r.get("type")) != "entityType"]
    rows, vecs, misses = [], [], 0
    for r in resources:
        v = cached_embedding(resource_text(r))
        if v is None:
            misses += 1
            continue
        rows.append(r)
        vecs.append(v)
    X = np.vstack(vecs)
    X = X / np.linalg.norm(X, axis=1, keepdims=True)  # L2-normalise -> dot == cosine
    print(f"[load] state={STATE}: {len(resources)} resources, {len(rows)} embedded, {misses} misses")
    return rows, X


def namespace_of(r: dict) -> str:
    return (r.get("ordId") or r.get("_ordId") or ":").split(":")[0]


def type_of(r: dict) -> str:
    return r.get("_rtype") or r.get("type") or "unknown"


# ── quantitative separation analysis (full-dim, no projection) ──────────────
def quantitative(rows, X):
    ns = np.array([namespace_of(r) for r in rows])
    C = X @ X.T  # cosine sim (X is L2-normalised)
    n = len(rows)
    iu = np.triu_indices(n, k=1)
    same = ns[iu[0]] == ns[iu[1]]
    within = C[iu][same]
    between = C[iu][~same]
    print("\n=== QUANTITATIVE: namespace separation (full 3072-dim cosine) ===")
    print(f"  within-namespace  cosine: mean={within.mean():.3f}  sd={within.std():.3f}  (n={within.size})")
    print(f"  between-namespace cosine: mean={between.mean():.3f}  sd={between.std():.3f}  (n={between.size})")
    print(f"  gap (within - between)  : {within.mean() - between.mean():+.3f}")

    from sklearn.metrics import silhouette_score
    # silhouette with cosine distance; label = namespace
    sil_ns = silhouette_score(X, ns, metric="cosine")
    ty = np.array([type_of(r) for r in rows])
    sil_ty = silhouette_score(X, ty, metric="cosine")
    print(f"  silhouette (namespace labels): {sil_ns:+.3f}   [>0 => systems cluster; ~0 => intermixed]")
    print(f"  silhouette (type labels)     : {sil_ty:+.3f}   [reference: types are known to separate]")

    # per-namespace: mean cosine of a resource to its OWN system vs. nearest other system
    print("\n  per-namespace mean within-cosine:")
    for u in sorted(set(ns)):
        mask = ns == u
        sub = C[np.ix_(mask, mask)]
        iu2 = np.triu_indices(mask.sum(), k=1)
        w = sub[iu2].mean() if iu2[0].size else float("nan")
        print(f"    {u:14s} n={mask.sum():3d}  within={w:.3f}")
    return sil_ns, sil_ty


# ── t-SNE projection + centroids ────────────────────────────────────────────
def tsne_plots(rows, X, sil_ns, sil_ty):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.manifold import TSNE

    perp = 30
    print(f"\n[t-SNE] perplexity={perp}, metric=cosine, seed={SEED} ...")
    emb = TSNE(
        n_components=2, perplexity=perp, metric="cosine",
        init="pca", random_state=SEED, max_iter=1000,
    ).fit_transform(X)

    ns = np.array([namespace_of(r) for r in rows])
    ty = np.array([type_of(r) for r in rows])

    def scatter(labels, fname, title, subtitle):
        uniq = sorted(set(labels))
        cmap = plt.get_cmap("tab10" if len(uniq) <= 10 else "tab20")
        fig, ax = plt.subplots(figsize=(7, 6))
        for i, u in enumerate(uniq):
            m = labels == u
            col = cmap(i % cmap.N)
            ax.scatter(emb[m, 0], emb[m, 1], s=18, alpha=0.45, color=col, label=u, linewidths=0)
            cx, cy = emb[m, 0].mean(), emb[m, 1].mean()
            ax.scatter([cx], [cy], s=260, marker="X", color=col,
                       edgecolors="black", linewidths=1.6, zorder=5)
        ax.set_title(f"{title}\n{subtitle}", fontsize=10)
        ax.set_xlabel("t-SNE 1"); ax.set_ylabel("t-SNE 2")
        ax.legend(fontsize=7, markerscale=1.2, ncol=2, loc="best", framealpha=0.9)
        fig.tight_layout()
        for ext in ("png", "pdf", "svg"):
            fig.savefig(OUT / f"{fname}.{ext}", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  wrote {fname}.{{png,pdf,svg}}")

    scatter(ns, f"tsne_by_namespace_{STATE}",
            f"Resources coloured by system (namespace) [{STATE}]",
            f"X = system centroid   |   namespace silhouette = {sil_ns:+.3f}")
    scatter(ty, f"tsne_by_type_{STATE}",
            f"Resources coloured by resource type [{STATE}]",
            f"X = type centroid   |   type silhouette = {sil_ty:+.3f}")


def main():
    rows, X = load()
    sil_ns, sil_ty = quantitative(rows, X)
    tsne_plots(rows, X, sil_ns, sil_ty)
    print("\nDone.")


if __name__ == "__main__":
    main()
