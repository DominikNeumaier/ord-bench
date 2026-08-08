#!/usr/bin/env python3
"""
Generate an INLINE pgfplots/TikZ 2x2 figure for the appendix (no bitmap).

Rows    = ORD state (clean / enriched)
Columns = colouring (by system namespace / by resource type)

Emits a complete LaTeX `figure*` block to stdout, using pgfplots `only marks`
scatters (one \addplot per group) plus a large X centroid per group. This
mirrors the style of the previous inline PCA figure so the paper stays
consistent (vector TikZ, not \includegraphics).

Uses the on-disk embedding cache (no API calls).

Run:
  EMBED_CACHE="/path/to/cache/embed" \
  python3 analysis/embedding_analysis/scripts/gen_tsne_tikz.py > /tmp/tsne_tikz.tex
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
from sklearn.manifold import TSNE  # noqa: E402
from sklearn.metrics import silhouette_score  # noqa: E402

CACHE = Path(os.environ.get("EMBED_CACHE", str(Path(__file__).resolve().parent.parent / "embed_cache")))
SEED = 42

NS_ORDER = ["corp.itsm", "emarsys.cx", "my.mes", "sap.ariba", "sap.crm",
            "sap.ehs", "sap.s4", "sap.sf", "siemens.plm", "workday.hcm"]
NS_COLOR = {  # tab10-like, reused from the old figure palette
    "corp.itsm": "nsA", "emarsys.cx": "nsB", "my.mes": "nsC", "sap.ariba": "nsD",
    "sap.crm": "nsE", "sap.ehs": "nsF", "sap.s4": "nsG", "sap.sf": "nsH",
    "siemens.plm": "nsI", "workday.hcm": "nsJ",
}
TY_ORDER = ["agent", "apiResource", "dataProduct"]
TY_COLOR = {"agent": "tpAgent", "apiResource": "tpApi", "dataProduct": "tpDp"}


def resource_text(r):
    parts = [r["title"], r["shortDescription"], r["description"]]
    g = r.get("partOfGroups") or []
    if g:
        parts.append("partOfGroups: " + ", ".join(x.get("groupId", "") for x in g if x.get("groupId")))
    n = r.get("processNext") or []
    if n:
        parts.append("processNext: " + ", ".join(n))
    c = r.get("capabilities") or []
    if c:
        parts.append("capabilities: " + ", ".join(c))
    u = r.get("useCases") or []
    if u:
        parts.append("useCases: " + " | ".join(u))
    return " | ".join(p for p in parts if p)


def _key(t):
    return hashlib.sha256(json.dumps({"model": config.EMBEDDING_MODEL, "text": t},
                                     sort_keys=True, default=str).encode()).hexdigest()


def emb_of(t):
    cp = CACHE / f"{_key(t)}.json"
    return np.asarray(json.loads(cp.read_text())["vec"], dtype=np.float64) if cp.exists() else None


def load(state):
    res = ord_loader.load_landscape(state=state)
    res = [r for r in res if (r.get("_rtype") or r.get("type")) != "entityType"]
    rows, vecs = [], []
    for r in res:
        v = emb_of(resource_text(r))
        if v is None:
            continue
        rows.append(r); vecs.append(v)
    X = np.vstack(vecs)
    X = X / np.linalg.norm(X, axis=1, keepdims=True)
    return rows, X


def ns_of(r):
    return (r.get("ordId") or r.get("_ordId") or ":").split(":")[0]


def ty_of(r):
    return r.get("_rtype") or r.get("type") or "unknown"


def tsne(X):
    return TSNE(n_components=2, perplexity=30, metric="cosine",
                init="pca", random_state=SEED, max_iter=1000).fit_transform(X)


def coords(emb, mask):
    return " ".join(f"({emb[i,0]:.3f},{emb[i,1]:.3f})" for i in np.where(mask)[0])


def axis_block(emb, labels, order, colmap, sil, xlabel, ylabel, tag, legend_cols, legend):
    lines = []
    lines.append(r"  \begin{tikzpicture}")
    lines.append(r"    \begin{axis}[")
    lines.append(r"      width=\linewidth, height=6.0cm,")
    lines.append(r"      xtick=\empty, ytick=\empty,")
    if xlabel:
        lines.append(r"      xlabel={" + xlabel + r"}, xlabel style={font=\scriptsize},")
    if ylabel:
        lines.append(r"      ylabel={" + ylabel + r"}, ylabel style={font=\scriptsize},")
    lines.append(r"      axis line style={draw=black!45},")
    lines.append(r"      title style={font=\scriptsize, yshift=-1pt},")
    lines.append(r"      title={silhouette $=" + f"{sil:+.2f}" + r"$ (" + tag + r")},")
    if legend:
        lines.append(r"      legend style={at={(0.5,-0.14)}, anchor=north, legend columns=" + str(legend_cols) + r",")
        lines.append(r"        draw=none, font=\scriptsize, /tikz/every even column/.append style={column sep=3pt}},")
        lines.append(r"      legend image code/.code={\draw[#1,fill=#1] (0.06cm,0) circle (1.6pt);},")
    lines.append(r"    ]")
    for u in order:
        m = labels == u
        if not m.any():
            continue
        col = colmap[u]
        lines.append(r"      \addplot[only marks, mark=*, mark size=1.0pt, draw=white, line width=0.1pt, fill="
                     + col + r", fill opacity=0.75] coordinates {" + coords(emb, m) + r"};")
        if legend:
            lines.append(r"      \addlegendentry{\texttt{" + u + r"}}")
        # centroid
        cx, cy = emb[m, 0].mean(), emb[m, 1].mean()
        lines.append(r"      \addplot[only marks, mark=x, mark size=3.6pt, "
                     + col + r", line width=1.4pt, forget plot] coordinates {("
                     + f"{cx:.3f},{cy:.3f}" + r")};")
    lines.append(r"    \end{axis}")
    lines.append(r"  \end{tikzpicture}")
    return "\n".join(lines)


def main():
    states = {}
    for st in ["clean", "enriched"]:
        rows, X = load(st)
        emb = tsne(X)
        ns = np.array([ns_of(r) for r in rows])
        ty = np.array([ty_of(r) for r in rows])
        states[st] = dict(
            emb=emb, ns=ns, ty=ty,
            sil_ns=silhouette_score(X, ns, metric="cosine"),
            sil_ty=silhouette_score(X, ty, metric="cosine"),
        )

    out = []
    # colour definitions (reused palette)
    palette = {
        "nsA": "2A78D6", "nsB": "EB6834", "nsC": "008300", "nsD": "E34948", "nsE": "1BAF7A",
        "nsF": "EDA100", "nsG": "4A3AA7", "nsH": "E87BA4", "nsI": "9D755D", "nsJ": "9A9A92",
        "tpAgent": "1BAF7A", "tpApi": "EB6834", "tpDp": "4A3AA7",
    }
    for name, hexv in palette.items():
        out.append(r"\definecolor{" + name + r"}{HTML}{" + hexv + r"}")

    out.append(r"\begin{figure*}[!t]")
    out.append(r"  \centering")
    out.append(r"  \captionsetup[subfigure]{position=top, skip=2pt}")

    panels = [
        ("clean", "ns", None, "Clean-ORD"),
        ("clean", "ty", None, None),
        ("enriched", "ns", None, "Enriched-ORD"),
        ("enriched", "ty", None, None),
    ]
    # column captions on top row only
    col_caption = {"ns": "By system (intermixed).", "ty": "By resource type (separated)."}

    for idx, (st, kind, _, rowlabel) in enumerate(panels):
        d = states[st]
        emb = d["emb"]
        labels = d[kind]
        top_row = idx < 2
        # subfigure
        out.append(r"  \begin{subfigure}[t]{0.49\textwidth}")
        out.append(r"  \centering")
        if top_row:
            out.append(r"  \caption{" + col_caption[kind] + r"}")
        ylabel = rowlabel if kind == "ns" else None  # row label on left column
        if kind == "ns":
            order, colmap, sil, tag, lc = NS_ORDER, NS_COLOR, d["sil_ns"], "intermixed", 5
        else:
            order, colmap, sil, tag, lc = TY_ORDER, TY_COLOR, d["sil_ty"], "separated", 3
        legend = not top_row  # legends only on bottom row to save space
        block = axis_block(emb, labels, order, colmap, sil,
                           xlabel=None, ylabel=ylabel, tag=tag,
                           legend_cols=lc, legend=legend)
        out.append(block)
        out.append(r"  \end{subfigure}")
        if idx % 2 == 0:
            out.append(r"  \hfill")

    out.append(r"  \caption{Post-hoc t-SNE projection of the 273 resource embeddings "
               r"(\texttt{text-embedding-3-large}, cosine metric, perplexity~30, seed~42), for the "
               r"Clean-ORD (top) and Enriched-ORD (bottom) states. Left column colours resources by "
               r"system namespace, right column by resource type; the large cross ($\times$) is each "
               r"group's centroid. \textbf{By system:} in both states the ten namespaces are thoroughly "
               r"intermixed and the system centroids collapse into a single central cloud (silhouette "
               r"$-0.04$): resources group by what they do, not by which system they belong to. "
               r"\textbf{By type:} resource types form distinct regions with well-separated centroids "
               r"(silhouette $+0.17$ / $+0.16$), matching the metric's cross-type penalty. The near-identical "
               r"silhouette scores across the clean and enriched states show that semantic enrichment adds "
               r"field-level context without reshaping the coarse similarity geometry.}")
    out.append(r"  \label{fig:embedding-validation-full}\end{figure*}")

    print("\n".join(out))


if __name__ == "__main__":
    main()
