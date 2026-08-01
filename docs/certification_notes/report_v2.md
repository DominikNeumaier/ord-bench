# Baseline-Solver Certification Report (v2)

## Method

Each of the 90 in-scope cases was run through Method S (no-retrieval LLM baseline) **5 independent times**.
Each run uses a unique per-run nonce in the prompt to bypass the LLM cache, so every run is a fresh API call. Full LLM input and raw output is stored per run under `v2/runs/<case_id>/run_<NN>.json`.

**Robust** = S solved in 0 of N runs (strictest definition).
**Borderline** = S solved in exactly 1 of N runs.
**Too easy** = S solved in 2+ runs.

## Results

| Category | Count | % |
|---|---|---|
| Robust (0/5 solved) | 82 | 91.1% |
| Borderline (1/5 solved) | 2 | 2.2% |
| Too easy ($\ge$2/5 solved) | 6 | 6.7% |
| **Total** | **90** | 100% |

Average difficulty: **0.9378**

## By Mode

| Mode | Total | Robust | Borderline | Too Easy |
|---|---|---|---|---|
| skill_guided | 30 | 30 | 0 | 0 |
| skill_adjusted | 20 | 18 | 0 | 2 |
| dynamic | 40 | 34 | 2 | 4 |

## Borderline Cases (1 solve out of 5)

- **dy-20** (dynamic) S solved 1/5
- **dy-40** (dynamic) S solved 1/5

## Too-Easy Cases ($\ge$2 solves)

- **sa-03** (skill_adjusted) S solved 2/5  _We need to prepare for launching our new product revision and ensure everything is ready for manufacturing. This include_
- **sa-17** (skill_adjusted) S solved 4/5  _We need to conduct a comprehensive review of our current compensation structure and analyze our total workforce costs ac_
- **dy-01** (dynamic) S solved 5/5  _I need to pull up a recent issue that one of our customers reported last week so I can see what we promised to deliver a_
- **dy-03** (dynamic) S solved 5/5  _I need to set up automated safety checks for our engineering change orders and material updates before they go to produc_
- **dy-14** (dynamic) S solved 5/5  _We need to record incoming shipments from our suppliers into the system, but I'm not sure if we should be using the invo_
- **dy-15** (dynamic) S solved 5/5  _Our finance team is struggling to reconcile payroll data across multiple departments because we can't easily track how i_
