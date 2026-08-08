# Disambiguation Experiment

**Question.** The design-time flow writes three semantic fields back into ORD
(`capabilities`, `partOfGroups`, `useCases`). Does adding those fields to the
similarity computation make ambiguous resource pairs easier to tell apart?

This is the *structural* counterpart to the retrieval results: methods that read
typed fields (C, D) gain under enrichment, embedding-based A does not. If the
semantic layer genuinely disambiguates, that should be visible in the ambiguity
metric itself — not only in downstream P@1.

## What it does

The benchmark's ambiguity metric (`src/adversarial/preselect.py`) scores resource
similarity over six ORD fields, none of them semantic. `extended_metric.py`
**extends** that metric with the three design-time fields, reusing the original
helpers verbatim so the only difference is the added dimensions. Two callables:

- `pairwise_original` — passthrough to `preselect._pairwise_sim`. Verified to
  reproduce the benchmark exactly: avg. HIGH-tier neighbours = **1.736** over all
  273 resources, identical to `landscape_ambiguity_report.json`.

  > **Why 1.736 and not the ~2.15 shown in the thesis convergence figure (Fig. 4):**
  > Fig. 4 is measured *during generation* with `_fast_sim`, which sets the
  > TF-IDF text dimension to 0 for O(1) speed (an explicit conservative lower
  > bound; see `generate_iterative.py`). This experiment — like the final
  > `landscape_ambiguity_report.json` — uses the **full** metric *with* TF-IDF
  > text, which is the metric that actually drives test-case selection. The two
  > numbers measure the same quantity with different similarity functions; 1.736
  > is the authoritative full-metric value. Original-vs-extended is compared on
  > the identical full base, so this choice does not affect the delta.

- `pairwise_extended` — same six base dimensions (fixed weight 1.0), plus
  `capabilities` (Jaccard), `partOfGroups` (Jaccard), `useCases` (TF-IDF cosine).
  **Both-sided normalisation:** a semantic dimension enters both numerator and
  denominator only when **both** resources carry that field. If either side lacks
  it, the dimension is skipped and the denominator stays at 6 — so a score can drop
  only because two resources that *both* describe capabilities / processes / use
  cases describe *different* ones, never because one side has metadata the other
  lacks and never from a larger fixed denominator.

`run_disambiguation.py` produces:

1. **HIGH-tier neighbour count, original vs extended metric**, for two populations:
   all 273 resources (consistent with Fig. 4) and the 70 enriched GT resources.
   Same tier (`sim >= 0.50`) the landscape-convergence figure tracks.
2. **Hardest-neighbour drop.** For each resource's most similar neighbour under the
   original metric: does the extended metric push it below the HIGH tier?
3. **Embedding counter-check** (no API — reads `cache/embed/` only). Nearest-
   neighbour embedding cosine on the clean Method-A text vs the enriched text.

## Scope — read this before citing the numbers

Two populations are reported. **All 273** is consistent with Fig. 4 (landscape-wide
average). **70 enriched GT** isolates the resources that carry the fields; they are
more ambiguous than average (they were selected as GT targets), so their original
HIGH-tier count (3.24) exceeds the landscape-wide 1.74. The delta is
original-vs-extended *on the same population*, so that baseline gap does not affect
it.

The denominator confound is removed by construction: with both-sided
normalisation, a pair whose partner is not enriched keeps the original 6-field
denominator and its score is unchanged. Of the 227 original HIGH pairs among the 70
enriched resources, 170 (75%) have an enriched partner (the extension can act); the
remaining 57 (25%) do not and stay HIGH. The "enriched pairs" view below averages
only over the 67 resources that have at least one enriched HIGH neighbour.

## Results (current landscape)

| Population | Avg. HIGH-tier neighbours (orig → ext) | Reduction |
|---|---|---|
| All 273 resources | 1.74 → 1.27 | −27% |
| 70 enriched GT resources (full neighbour pool) | 3.24 → 1.41 | −56% |
| 67 enriched pairs (enriched neighbours only) | 2.54 → 0.63 | −75% |

Embedding counter-check (70 enriched resources): mean NN cosine *rises* from 0.799
(clean) to 0.824 (enriched), `mean_delta = +0.025`; only 14.3% of resources are
pulled apart. The enriched embedding makes nearest neighbours *more* similar.

**Reading.** When both resources carry semantic fields and those fields differ, the
structural metric separates them (−56% HIGH pairs on the enriched set). Averaging
the same fields into one embedding vector instead moves neighbours together
(+0.025 cosine). This is the mechanism behind the retrieval results — structural
methods (C, D) exploit the separation, embedding-based A suffers the dilution.

## Run

```
python analysis/disambiguation/run_disambiguation.py   # writes output/disambiguation_report.json
python analysis/disambiguation/make_charts.py          # writes output/fig_*.pdf + .png
```

No API calls. Embeddings are read from the on-disk cache populated by prior
Method-A runs; the script reports cache coverage and skips misses.

## Files

- `extended_metric.py` — original metric + three semantic dimensions
- `run_disambiguation.py` — the three analyses → `output/disambiguation_report.json`
- `make_charts.py` — `output/fig_high_tier.pdf`, `output/fig_embedding.pdf`

This directory is self-contained and does not modify the main thesis pipeline.
