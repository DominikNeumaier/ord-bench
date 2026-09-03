# ORD-Bench

**An adversarially constructed benchmark for enterprise resource selection.**

ORD-Bench provides a typed enterprise resource landscape with controlled ambiguity, paired Clean-ORD/Enriched-ORD descriptions, and 350 design-time and runtime test cases.

## Contents

- **273 resources across 10 systems** in ORD v1.16-shaped documents
- **30 process models and 30 skills** used for process-derived enrichment
- **240 design-time cases** and **110 runtime cases**
- deterministic structural ambiguity analyses and committed paper artefacts

```text
src/                         benchmark construction, validation, certification
data/                        canonical benchmark artefacts and construction logs
analysis/                    analysis scripts and derived results
analysis/certification/      post-hoc certification outputs
web/                         static benchmark browser
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[analysis,dev]"
```

Generation and certification use an OpenAI-compatible endpoint configured through `.env` or environment variables:

```bash
LLM_BASE_URL=...
LLM_API_KEY=...
LLM_MODEL=anthropic--claude-4.5-haiku
EMBEDDING_BASE_URL=...
EMBEDDING_MODEL=text-embedding-3-large
```

## Verify the committed benchmark

These checks are offline and do not call an LLM:

```bash
python3 -m unittest discover -s tests
python3 -m src.loader
python3 analysis/test_cases/test_case_stats.py
```

Expected headline counts are 273 resources, 10 systems, 240 design-time cases, 110 runtime cases, and 30 skills.

## Regenerate analyses

The following commands write derived files under `analysis/` and may overwrite committed outputs:

```bash
python3 analysis/disambiguation/run_disambiguation.py
python3 analysis/embedding_analysis/scripts/embedding_by_tier.py
python3 analysis/embedding_analysis/scripts/embedding_stats.py
```

`run_disambiguation.py` reproduces the reported mean structural changes (-24.5% overall enriched pairs and -28.3% for the previous HIGH subset). `embedding_stats.py` reports the structural/embedding correlation; `embedding_by_tier.py` regenerates the tier plot.

## Repository boundary

ORD-Bench owns benchmark data, generation, validation, and benchmark analyses. Retrieval algorithms and their evaluation live in the separate `semantic-retrieval` repository. ORD-Bench does not import that repository; its construction gate uses the frozen baseline in `src/certification/baseline_solver.py`.

## Paper

*ORD-Bench: An Adversarially Constructed Benchmark for Enterprise Resource Selection*, Neumaier, 2026. The paper source is maintained with the thesis and is not part of this repository checkout.
