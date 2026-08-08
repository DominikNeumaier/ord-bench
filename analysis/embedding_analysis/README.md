# Embedding analysis

Validates the field-based ambiguity metric against a raw embedding model
(`text-embedding-3-large`) and produces the paper's embedding figures.

## Layout

```
scripts/       reproduction scripts (run these)
output/        generated artefacts (figures, pairwise.csv, fig10_data.json)
  pca_unused/  PCA cluster plots — kept for reference, NOT used in the paper
embed_cache/   343 bundled embedding vectors (zero API calls needed)
```

## Scripts

| Script | Produces | Paper |
|---|---|---|
| `embedding_vs_metric.py` | `output/pairwise.csv`, scatter, Pearson/Spearman r | r=0.63 |
| `embedding_stats.py` | r + per-tier median cosine, from `pairwise.csv` | Fig. 5 numbers |
| `embedding_by_tier.py` | `output/embedding_by_tier.{pdf,png}` | Fig. 5 |
| `make_fig_embedding_groups.py` | `output/embedding_clean_vs_enriched.{pdf,png}` | Fig. 6 |
| `gen_tsne_tikz.py` | t-SNE TikZ fragment + silhouette scores (stdout) | Appendix E.1 |
| `tsne_by_namespace.py`, `tsne_grid.py` | t-SNE renders | Appendix E.1 |

## Reproduce

```bash
python3 scripts/embedding_vs_metric.py        # -> output/pairwise.csv (needs embed_cache/)
python3 scripts/embedding_stats.py            # r=0.63, tier medians 0.35 -> 0.74
python3 scripts/embedding_by_tier.py          # Fig. 5
python3 scripts/make_fig_embedding_groups.py  # Fig. 6
python3 scripts/gen_tsne_tikz.py              # Appendix E.1 fragment
```

All scripts read embeddings from `embed_cache/` (bundled) and make zero API calls.
