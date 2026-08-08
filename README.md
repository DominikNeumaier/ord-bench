# ORD-Bench

**An adversarially constructed benchmark for enterprise resource selection.**

Enterprise agents must identify the right resource among many semantically similar alternatives across heterogeneous systems. Whether structured, semantically enriched resource descriptions actually reduce this ambiguity has not been measurable — no benchmark provided typed enterprise resources with controlled ambiguity and paired enriched/non-enriched states. ORD-Bench fills this gap.

## Contributions

1. **Typed enterprise landscape** — 273 resources across 10 systems (SAP, Workday, Siemens, and others), represented natively in Open Resource Discovery (ORD) v1.16.
2. **Adversarial ambiguity metric** — a field-based similarity metric over six ORD dimensions that drives an iterative construction loop placing graded distractors around every target resource. Difficulty is a controlled property, not a by-product of catalogue size.
3. **Process-derived semantic enrichment** — 30 BPMN/CMMN process models matched to landscape resources, writing four typed semantic fields (`capabilities`, `useCases`, `partOfGroups`, `processNext`) back into each resource. Produces paired Clean-ORD and Enriched-ORD states over the same fixed landscape.
4. **350 test cases** — split into design-time (activity-to-resource matching) and runtime families (Skill-Guided, Skill-Adjusted, Dynamic, Out-of-Scope), reusable as a substrate for retrieval and selection studies.

**Key finding:** Semantic enrichment lowers structural ambiguity by up to 28.3% on the most confusable pairs, yet raises embedding-based similarity by 27.7% on the same pairs — ambiguity is a property of the retrieval representation, not the resource.

## Structure

```
src/            Benchmark construction code (ambiguity metric, adversarial loop, case builder)
data/
  landscape/    273 ORD resources, clean and enriched (systems/, systems_enriched/)
  test_cases/   350 test cases (design_time/, runtime/)
  ambiguity/    Pairwise ambiguity report
  certification/ Test-case difficulty certification harness
analysis/    Reproduction scripts and figures (disambiguation analysis, embedding validation)
paper/          Conference paper LaTeX source and PDF
docs/           Design documentation
web/            Interactive benchmark browser (landscape, ambiguity, test cases)
```

## Reproducing the numbers

```bash
python analysis/disambiguation/run_disambiguation.py   # -24.5% / -28.3% structural ambiguity
python analysis/embedding_analysis/scripts/embedding_by_tier.py  # r=0.63
```

## Paper

*ORD-Bench: An Adversarially Constructed Benchmark for Enterprise Resource Selection*, Neumaier, 2026.
