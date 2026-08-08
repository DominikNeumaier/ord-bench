"""Reproduce the embedding-vs-structural-metric statistics (Paper I, Fig. 5 + text).

Reads the frozen pairwise table (analysis/embedding_analysis/pairwise.csv) — one
row per resource pair with its structural similarity and its embedding cosine
(text-embedding-3-large). That table is the on-disk snapshot of the embedding
comparison; this script derives every reported number from it, with no API call
and no embedding cache required.

  Correlation (paper: r = 0.63)
      Pearson and Spearman between structural_sim and embedding_cos over all
      pairs.

  Per-tier embedding cosine (paper: median rises 0.35 -> 0.74; Fig. 5)
      Pairs are bucketed by their structural tier
          HIGH  >= 0.50   MEDIUM 0.25-0.50   LOW 0.10-0.25   NONE < 0.10
      (half-open intervals, same as src/generation/generate_iterative.py), and
      the count + median embedding cosine is reported per tier.

How pairwise.csv is produced (needs the embedding cache, so not re-run here):
    python3 analysis/embedding_analysis/scripts/embedding_vs_metric.py
    That script reads cache/embed/ (text-embedding-3-large vectors, keyed by the
    same hash llm.embed uses) and writes pairwise.csv. It makes no API calls of
    its own but requires the cache to be populated first (by Method A / any prior
    embedding run).

Run:  python3 analysis/embedding_analysis/embedding_stats.py
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "output"
PAIRWISE = HERE / "pairwise.csv"


def load_pairs() -> tuple[list[float], list[float]]:
    xs, ys = [], []
    with PAIRWISE.open() as f:
        for row in csv.DictReader(f):
            xs.append(float(row["structural_sim"]))
            ys.append(float(row["embedding_cos"]))
    return xs, ys


def _pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return cov / (sa * sb) if sa and sb else 0.0


def _rank(v: list[float]) -> list[float]:
    order = sorted(range(len(v)), key=lambda i: v[i])
    ranks = [0.0] * len(v)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _spearman(a: list[float], b: list[float]) -> float:
    return _pearson(_rank(a), _rank(b))


def _tier(s: float) -> str:
    if s >= 0.50:
        return "HIGH"
    if s >= 0.25:
        return "MEDIUM"
    if s >= 0.10:
        return "LOW"
    return "NONE"


def _median(v: list[float]) -> float:
    s = sorted(v)
    n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def main() -> None:
    xs, ys = load_pairs()
    n = len(xs)

    print(f"pairs (from pairwise.csv): {n}")
    print(f"Pearson  r (structural vs embedding cosine): {_pearson(xs, ys):.4f}")
    print(f"Spearman r:                                  {_spearman(xs, ys):.4f}")
    print()

    by_tier: dict[str, list[float]] = {"HIGH": [], "MEDIUM": [], "LOW": [], "NONE": []}
    for s, c in zip(xs, ys):
        by_tier[_tier(s)].append(c)

    print(f"{'tier':7} {'range':12} {'n':>6} {'median cos':>11}")
    ranges = {"HIGH": ">=0.50", "MEDIUM": "0.25-0.50",
              "LOW": "0.10-0.25", "NONE": "<0.10"}
    for t in ("HIGH", "MEDIUM", "LOW", "NONE"):
        v = by_tier[t]
        print(f"{t:7} {ranges[t]:12} {len(v):>6} {_median(v):>11.4f}")


if __name__ == "__main__":
    main()
