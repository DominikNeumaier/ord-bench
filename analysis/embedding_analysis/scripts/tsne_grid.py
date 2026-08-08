#!/usr/bin/env python3
"""
Combined 2x2 t-SNE panel for the appendix.

Rows    = ORD state (clean / enriched)
Columns = colouring (by system namespace / by resource type)

Answers two questions in one figure:
  - Do systems cluster, or are they intermixed? (namespace column)
  - Does the semantic enrichment change this geometry? (clean vs enriched rows)

Uses the on-disk embedding cache (no API calls). Same hash key as llm.embed.

Run:
  EMBED_CACHE="/path/to/cache/embed" \
  python3 analysis/embedding_analysis/scripts/tsne_grid.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from src import config, loader as ord_loader  # noqa: E402

OUT = ROOT / "analysis" / "embedding_analysis"
CACHE = Path(os.environ.get("EMBED_CACHE", str(Path(__file__).resolve().parent.parent / "embed_cache")))
SEED = 42


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


def cached_embedding(text: str):
    cp = CACHE / f"{_key(text)}.json"
    if not cp.exists():
        return None
    return np.asarray(json.loads(cp.read_text())["vec"], dtype=np.float64)


def load(state):
    resources = ord_loader.load_landscape(state=state)
    resources = [r for r in resources if (r.get("_rtype") or r.get("type")) != "entityType"]
    rows, vecs = [], []
    for r in resources:
        v = cached_embedding(resource_text(r))
        if v is None:
            continue
        rows.append(r)
        vecs.append(v)
    X = np.vstack(vecs)
    X = X / np.linalg.norm(X, axis=1, keepdims=True)
    return rows, X


def ns_of(r):
    return (r.get("ordId") or r.get("_ordId") or ":").split(":")[0]


def type_of(r):
    return r.get("_rtype") or r.get("type") or "unknown"


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.manifold import TSNE
    from sklearn.metrics import silhouette_score

    states = ["clean", "enriched"]
    data = {}
    print("Computing t-SNE (seed=42, metric=cosine) ...")
    for st in states:
        rows, X = load(st)
        emb = TSNE(n_components=2, perplexity=30, metric="cosine",
                   init="pca", random_state=SEED, max_iter=1000).fit_transform(X)
        ns = np.array([ns_of(r) for r in rows])
        ty = np.array([type_of(r) for r in rows])
        sil_ns = silhouette_score(X, ns, metric="cosine")
        sil_ty = silhouette_score(X, ty, metric="cosine")
        data[st] = dict(emb=emb, ns=ns, ty=ty, sil_ns=sil_ns, sil_ty=sil_ty, n=len(rows))
        print(f"  {st}: n={len(rows)}  sil(ns)={sil_ns:+.3f}  sil(type)={sil_ty:+.3f}")

    ns_labels = sorted(set(data["clean"]["ns"]))
    ty_labels = sorted(set(data["clean"]["ty"]))
    ns_cmap = plt.get_cmap("tab10")
    ty_cmap = plt.get_cmap("Set2")
    ns_col = {u: ns_cmap(i % 10) for i, u in enumerate(ns_labels)}
    ty_col = {u: ty_cmap(i) for i, u in enumerate(ty_labels)}

    fig, axes = plt.subplots(2, 2, figsize=(9.2, 8.6))

    def panel(ax, emb, labels, colmap, sil, show_ylabel, show_title, col_kind):
        for u in sorted(set(labels)):
            m = labels == u
            c = colmap[u]
            ax.scatter(emb[m, 0], emb[m, 1], s=14, alpha=0.45, color=c, linewidths=0)
            ax.scatter([emb[m, 0].mean()], [emb[m, 1].mean()], s=190, marker="X",
                       color=c, edgecolors="black", linewidths=1.4, zorder=5)
        ax.set_xticks([]); ax.set_yticks([])
        tag = "intermixed" if col_kind == "ns" else "separated"
        ax.text(0.5, 0.985, f"silhouette = {sil:+.3f}  ({tag})",
                transform=ax.transAxes, ha="center", va="top", fontsize=8.5,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="black", alpha=0.75, lw=0.5))

    for row, st in enumerate(states):
        d = data[st]
        panel(axes[row, 0], d["emb"], d["ns"], ns_col, d["sil_ns"], True, row == 0, "ns")
        panel(axes[row, 1], d["emb"], d["ty"], ty_col, d["sil_ty"], False, row == 0, "ty")

    # column headers
    axes[0, 0].set_title("Coloured by system (namespace)", fontsize=11)
    axes[0, 1].set_title("Coloured by resource type", fontsize=11)
    # row labels
    axes[0, 0].set_ylabel("Clean-ORD", fontsize=11)
    axes[1, 0].set_ylabel("Enriched-ORD", fontsize=11)

    # shared legends
    from matplotlib.lines import Line2D
    ns_handles = [Line2D([0], [0], marker="o", color="w", markerfacecolor=ns_col[u],
                         markersize=7, label=u) for u in ns_labels]
    ty_handles = [Line2D([0], [0], marker="o", color="w", markerfacecolor=ty_col[u],
                         markersize=7, label=u) for u in ty_labels]
    cx_handle = [Line2D([0], [0], marker="X", color="w", markerfacecolor="grey",
                        markeredgecolor="black", markersize=10, label="group centroid")]
    fig.legend(handles=ns_handles + cx_handle, loc="lower left", ncol=6, fontsize=8,
               bbox_to_anchor=(0.02, -0.005), frameon=False, columnspacing=1.0)
    fig.legend(handles=ty_handles, loc="lower right", ncol=3, fontsize=8,
               bbox_to_anchor=(0.99, -0.005), frameon=False)

    fig.tight_layout(rect=(0, 0.06, 1, 1))
    for ext in ("pdf", "png", "svg"):
        fig.savefig(OUT / f"tsne_grid.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nWrote tsne_grid.{{pdf,png,svg}} to {OUT}")


if __name__ == "__main__":
    main()
