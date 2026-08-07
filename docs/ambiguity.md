# Benchmark: Ambiguity Scoring

## What this does

Every ORD resource in the landscape gets a structural **ambiguity score** — a number between 0 and 1 that measures how hard it is to distinguish from its nearest neighbors, using only the typed ORD fields (no LLM, fully deterministic).

The score is the mean similarity to the top-5 most similar resources, computed across five dimensions:

| Field | Method | Weight | Rationale |
|---|---|---|---|
| `useCases` | TF-IDF cosine | 3.5 | Natural language closest to user prompts; 100% filled |
| `entityTypes` | IDF-weighted Jaccard | 2.5 | Shared business objects = genuine confusion risk |
| `capabilities` | Jaccard | 1.0 | Functional overlap; only 25% filled for APIs |
| `tags` | Jaccard | 1.0 | Keyword signal; 100% filled |
| `lineOfBusiness` | Jaccard | 1.0 | Domain similarity |
| cross-namespace | bonus | 0.5 | P1: same domain, different vendor |

A **type penalty of ×0.5** is applied when two resources have different types (e.g. agent vs. dataProduct), because a user asking for an action will not confuse an executable agent with a read-only data product.

**IDF** on entityTypes: very common entity types like `Employee:v1` (appearing in many resources) get lower weight than rare domain-specific ones.

## Difficulty bands

| Band | Score range | Meaning |
|---|---|---|
| easy | < 0.20 | Few confusable resources — trivially unique |
| medium | 0.20–0.40 | Some overlap — standard difficulty |
| hard | 0.40–0.60 | Genuinely ambiguous — good test cases |
| very_hard | ≥ 0.60 | Highly confusable — hardest cases |

**Coverage gap**: a resource with no neighbors above the 0.25 threshold. No non-trivial test case can be generated for it without landscape enrichment.

## How to run

```bash
# From repo root
python3 src/ambiguity/run_ambiguity.py

# With options
python3 src/ambiguity/run_ambiguity.py --top-k 5 --min-score 0.25 --state enriched
```

Output: `data/ambiguity/landscape_ambiguity_report.json`

## Output format

```json
{
  "summary": {
    "total_resources": 177,
    "easy": 55, "medium": 110, "hard": 12, "very_hard": 0,
    "coverage_gaps": 44,
    "weights_used": { ... }
  },
  "by_namespace": { ... },
  "top_ambiguous_pairs": [ ... ],
  "resources": [
    {
      "ordId": "sap.sf:agent:HRChatbot:v1",
      "ambiguity_score": 0.3466,
      "difficulty_band": "medium",
      "top_neighbors": [ ... ],
      "all_neighbors": [ ... 176 entries with full breakdown ... ],
      "coverage_gap": false
    }
  ]
}
```

The `all_neighbors` array contains all 176 pairwise scores with a full breakdown per dimension — every number is reproducible from the ORD fields alone.
