# Baseline-Solver Certification

## Purpose

During benchmark construction, each runtime in-scope case was accepted only if
Method S (the no-retrieval LLM baseline) failed to solve it in a single run.
Because S is non-deterministic, a single-run gate could admit cases that S would
solve in other runs (sampling noise).

This folder contains a **post-hoc multi-run certification** that re-runs S on every
accepted in-scope case 4 additional times (total = original gate run + 4 = **5 runs**
per case).

A case is considered **robustly certified** if S fails in ≥ 4/5 runs (difficulty ≥ 0.80).
Cases where S succeeds in 2+ of the 5 runs are flagged as **borderline**.

## Files

| File | Description |
|---|---|
| `runs/` | Per-case raw traces for each of the 4 extra runs |
| `results.jsonl` | One line per case — case_id, mode, prompt, 5 run outcomes, difficulty score |
| `summary.json` | Aggregate statistics: % robustly certified, borderline cases |
| `report.md` | Human-readable summary for the thesis |

## How to read difficulty

```
difficulty = (number of runs where S failed) / (total runs = 5)

1.0   → S never solved it across 5 runs → very hard
0.80  → S solved it once in 5 runs       → robustly certified
0.60  → S solved it twice in 5 runs      → borderline
≤0.40 → S solved it 3+ times             → too easy, should have been excluded
```

## Script

```bash
python src/certification/run_certification_v2.py
```
