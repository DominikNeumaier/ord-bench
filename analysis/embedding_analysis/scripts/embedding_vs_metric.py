"""Ad-hoc analysis: does the structural ambiguity metric agree with the
raw embedding geometry, and do the embeddings form visible clusters?

Two independent notions of "how similar are two ORD resources":

  1. structural sim  — src/adversarial/preselect.py  (TF-IDF text + localId +
     entityTypes-IDF + LoB/tags/industry + type-penalty + cross-ns bonus).
     No LLM. This is the metric that drives distractor selection.

  2. embedding cosine — cosine between text-embedding-3-large vectors of the
     Method-A resource text. This is what Method A actually retrieves on.

We pull the embeddings straight from the on-disk cache (cache/embed/), keyed
by the same hash llm.embed uses, so this makes ZERO API calls.

Outputs (to analysis/embedding_analysis/):
  - correlation printed to stdout (Pearson + Spearman over all pairs)
  - scatter_metric_vs_embedding.html/.png
  - embedding_pca_clusters.html/.png   (PCA-2D, colored by namespace & type)
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src import config
from src import loader as ord_loader
from src.adversarial import preselect

OUT = Path(__file__).resolve().parent.parent
OUT.mkdir(parents=True, exist_ok=True)


# Inlined verbatim from src/methods/method_a._resource_text so we don't import
# method_a (which pulls in the openai client and hangs on this venv). Keep in
# sync if the real one changes.
def resource_text(r: dict) -> str:
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
    use_cases = r.get("useCases") or []
    if use_cases:
        parts.append("useCases: " + " | ".join(use_cases))
    return " | ".join(p for p in parts if p)


# ── embedding cache access (no API) ────────────────────────────────────────

def _hash(payload) -> str:
    s = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(s.encode()).hexdigest()


def cached_embedding(text: str) -> np.ndarray | None:
    key = _hash({"model": config.EMBEDDING_MODEL, "text": text})
    cp = config.CACHE_DIR / "embed" / f"{key}.json"
    if not cp.exists():
        return None
    return np.asarray(json.loads(cp.read_text())["vec"], dtype=np.float64)


# ── load landscape + embeddings ────────────────────────────────────────────

def load(state: str = "enriched"):
    resources = ord_loader.load_landscape(state=state)
    # keep only retrieval resources (drop entityType), same as preselect
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
    # L2-normalize so dot == cosine
    X = X / np.linalg.norm(X, axis=1, keepdims=True)
    print(f"[load] state={state}: {len(resources)} resources, "
          f"{len(rows)} with cached embedding, {misses} misses")
    return rows, X


# ── structural sim matrix (reuse preselect internals) ──────────────────────

def structural_matrix(rows: list[dict]) -> np.ndarray:
    idf = preselect._et_idf(rows)
    tfidf = preselect._build_tfidf_index(rows)
    n = len(rows)
    S = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            sim, _ = preselect._pairwise_sim(rows[i], rows[j], idf, tfidf)
            S[i, j] = S[j, i] = sim
    return S


# ── correlation ─────────────────────────────────────────────────────────────

def _pearson(a, b):
    a = a - a.mean(); b = b - b.mean()
    return float((a @ b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _rank(x):
    order = x.argsort()
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(len(x))
    # average ties
    _, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
    csum = np.cumsum(counts)
    start = csum - counts
    avg = (start + csum - 1) / 2.0
    return avg[inv]


def _spearman(a, b):
    return _pearson(_rank(a), _rank(b))


def correlate(rows, X):
    S = structural_matrix(rows)
    C = X @ X.T  # embedding cosine matrix
    iu = np.triu_indices(len(rows), k=1)
    s = S[iu]
    c = C[iu]
    print("\n=== correlation over all "
          f"{len(s):,} resource pairs ===")
    print(f"  structural sim : mean={s.mean():.3f}  sd={s.std():.3f}  "
          f"min={s.min():.3f}  max={s.max():.3f}")
    print(f"  embedding cos  : mean={c.mean():.3f}  sd={c.std():.3f}  "
          f"min={c.min():.3f}  max={c.max():.3f}")
    print(f"  Pearson  r = {_pearson(s, c):.3f}")
    print(f"  Spearman ρ = {_spearman(s, c):.3f}")

    # agreement on the "high similarity" tail — the part the metric is used for
    for thr in (0.25, 0.40, 0.60):
        mask = s >= thr
        if mask.sum() >= 3:
            print(f"  pairs with structural sim >= {thr:.2f}: n={mask.sum():4d}  "
                  f"mean embedding cos = {c[mask].mean():.3f}  "
                  f"(vs {c[~mask].mean():.3f} for the rest)")
    return S, C, s, c


# ── PCA via SVD (numpy only) ─────────────────────────────────────────────────

def pca_2d(X):
    Xc = X - X.mean(axis=0, keepdims=True)
    U, Sg, Vt = np.linalg.svd(Xc, full_matrices=False)
    coords = Xc @ Vt[:2].T
    ev = (Sg ** 2)
    var = ev[:2] / ev.sum()
    return coords, var


# ── simple k-means (numpy only, deterministic) ───────────────────────────────

def kmeans(X, k, iters=50):
    # deterministic init: k points spread by farthest-first
    idx = [0]
    d = np.full(len(X), np.inf)
    for _ in range(1, k):
        d = np.minimum(d, 1 - X @ X[idx[-1]])
        idx.append(int(d.argmax()))
    C = X[idx].copy()
    labels = np.zeros(len(X), dtype=int)
    for _ in range(iters):
        sim = X @ C.T
        new = sim.argmax(axis=1)
        if (new == labels).all():
            break
        labels = new
        for c in range(k):
            m = labels == c
            if m.any():
                v = X[m].mean(axis=0)
                C[c] = v / (np.linalg.norm(v) + 1e-12)
    return labels


# ── SVG rendering (pure python — plotly/matplotlib hang on this venv) ────────

# Okabe-Ito + extension: colorblind-safe categorical palette
PALETTE = [
    "#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2",
    "#EECA3B", "#B279A2", "#FF9DA6", "#9D755D", "#BAB0AC",
]


def _svg_header(w, h):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" font-family="Helvetica,Arial,sans-serif">'
            f'<rect width="{w}" height="{h}" fill="white"/>')


def _scale(v, lo, hi, a, b):
    if hi == lo:
        return (a + b) / 2
    return a + (v - lo) / (hi - lo) * (b - a)


# ── Shared layout so all three panels are pixel-identical ────────────────────
# Every panel uses the same canvas, the same plot rectangle, the same frame,
# the same 5×5 faint grid and the same fonts. The only thing that differs is
# what goes into the plot box and the legend band beneath it. This is what
# makes the three subfigures line up when tiled at equal width.
W = H = 600
ML, MR, MT = 90, 24, 24          # plot-box margins (left/right/top)
PY_BOT = 424                     # plot-box bottom (fixed → identical box height)
PX0, PX1 = ML, W - MR
PY_TOP = MT
GRID_FRACS = [0.0, 0.25, 0.50, 0.75, 1.0]
FS_TICK, FS_AXIS, FS_LEG, FS_ANNOT = 18, 20, 17, 19
XLBL_Y = PY_BOT + 42             # x-axis label baseline
LEG_Y0 = PY_BOT + 70             # first legend row baseline (fits up to 4 rows)
LEG_DY = 26                      # legend row pitch


def _frame(parts):
    """Left+bottom axes plus the shared faint 5×5 grid. No tick labels."""
    parts.append(f'<line x1="{PX0}" y1="{PY_BOT}" x2="{PX1}" y2="{PY_BOT}" stroke="#333" stroke-width="1.4"/>')
    parts.append(f'<line x1="{PX0}" y1="{PY_BOT}" x2="{PX0}" y2="{PY_TOP}" stroke="#333" stroke-width="1.4"/>')
    for f in GRID_FRACS:
        gx = _scale(f, 0, 1, PX0, PX1)
        gy = _scale(f, 0, 1, PY_BOT, PY_TOP)
        parts.append(f'<line x1="{gx}" y1="{PY_BOT}" x2="{gx}" y2="{PY_TOP}" stroke="#eee" stroke-width="1"/>')
        parts.append(f'<line x1="{PX0}" y1="{gy}" x2="{PX1}" y2="{gy}" stroke="#eee" stroke-width="1"/>')


def _axis_labels(parts, xlabel, ylabel):
    parts.append(f'<text x="{(PX0+PX1)/2}" y="{XLBL_Y}" text-anchor="middle" font-size="{FS_AXIS}">{xlabel}</text>')
    parts.append(f'<text x="26" y="{(PY_BOT+PY_TOP)/2}" text-anchor="middle" font-size="{FS_AXIS}" '
                 f'transform="rotate(-90 26 {(PY_BOT+PY_TOP)/2})">{ylabel}</text>')


def scatter_svg(x, y, path, xlabel, ylabel, r_pear, r_spear):
    xlo, xhi = 0.0, 0.8
    ylo, yhi = 0.0, 1.0
    parts = [_svg_header(W, H)]
    _frame(parts)
    # numeric tick labels on the shared grid positions
    for f in GRID_FRACS:
        gx = _scale(f, 0, 1, PX0, PX1)
        gy = _scale(f, 0, 1, PY_BOT, PY_TOP)
        parts.append(f'<text x="{gx}" y="{PY_BOT+26}" text-anchor="middle" font-size="{FS_TICK}">{xlo+f*(xhi-xlo):.1f}</text>')
        parts.append(f'<text x="{PX0-10}" y="{gy+6}" text-anchor="end" font-size="{FS_TICK}">{ylo+f*(yhi-ylo):.1f}</text>')
    for xi, yi in zip(x, y):
        cx = _scale(min(xi, xhi), xlo, xhi, PX0, PX1)
        cy = _scale(yi, ylo, yhi, PY_BOT, PY_TOP)
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.0" fill="#4C78A8" fill-opacity="0.28"/>')
    _axis_labels(parts, xlabel, ylabel)
    parts.append(f'<text x="{PX0+12}" y="{PY_TOP+26}" font-size="{FS_ANNOT}" fill="#333">'
                 f'r = {r_pear:.2f},  ρ = {r_spear:.2f}</text>')
    parts.append('</svg>')
    Path(path).write_text("".join(parts))


def cluster_svg(coords, labels, label_names, path, var):
    parts = [_svg_header(W, H)]
    _frame(parts)
    xlo, xhi = float(coords[:, 0].min()), float(coords[:, 0].max())
    ylo, yhi = float(coords[:, 1].min()), float(coords[:, 1].max())
    pad_x = (xhi - xlo) * 0.06 or 1
    pad_y = (yhi - ylo) * 0.06 or 1
    xlo, xhi = xlo - pad_x, xhi + pad_x
    ylo, yhi = ylo - pad_y, yhi + pad_y
    cats = label_names
    cmap = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(cats)}
    for (xi, yi), lab in zip(coords, labels):
        cx = _scale(xi, xlo, xhi, PX0, PX1)
        cy = _scale(yi, ylo, yhi, PY_BOT, PY_TOP)
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" '
                     f'fill="{cmap[lab]}" fill-opacity="0.80" stroke="white" stroke-width="0.7"/>')
    _axis_labels(parts, f"PC1 ({var[0]*100:.1f}%)", f"PC2 ({var[1]*100:.1f}%)")
    # horizontal legend beneath the plot box, 3 per row, in the shared band
    col_w = (PX1 - PX0) / 3
    for i, c in enumerate(cats):
        row, col = divmod(i, 3)
        lx = PX0 + col * col_w + 6
        ly = LEG_Y0 + row * LEG_DY
        parts.append(f'<circle cx="{lx}" cy="{ly}" r="7" fill="{cmap[c]}"/>')
        parts.append(f'<text x="{lx+14}" y="{ly+6}" font-size="{FS_LEG}">{c}</text>')
    parts.append('</svg>')
    Path(path).write_text("".join(parts))


def plot(rows, X, S, C, s, c):
    rng = np.random.default_rng(0)
    take = rng.choice(len(s), size=min(4000, len(s)), replace=False)
    scatter_svg(
        s[take], c[take],
        OUT / "scatter_metric_vs_embedding.svg",
        "structural ambiguity sim",
        "embedding cosine",
        _pearson(s, c), _spearman(s, c),
    )

    coords, var = pca_2d(X)
    ns = [r.get("namespace", "?") for r in rows]
    typ = [r.get("type", "?") for r in rows]
    cluster_svg(coords, ns, sorted(set(ns)),
                OUT / "embedding_pca_by_namespace.svg", var)
    cluster_svg(coords, typ, sorted(set(typ)),
                OUT / "embedding_pca_by_type.svg", var)

    # dump the pairwise data too, for any downstream stats
    iu = np.triu_indices(len(rows), k=1)
    import csv as _csv
    with open(OUT / "pairwise.csv", "w", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["ordId_A", "ordId_B", "structural_sim", "embedding_cos"])
        for a, b in zip(*iu):
            w.writerow([rows[a]["ordId"], rows[b]["ordId"],
                        f"{S[a,b]:.4f}", f"{C[a,b]:.4f}"])

    print(f"[done] SVG + pairwise.csv in {OUT}")
    return coords, var


if __name__ == "__main__":
    state = sys.argv[1] if len(sys.argv) > 1 else "enriched"
    rows, X = load(state)
    S, C, s, c = correlate(rows, X)
    plot(rows, X, S, C, s, c)
