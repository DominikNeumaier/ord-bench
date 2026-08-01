# Baseline-Solver Certification Report

## Method

Each of the 90 in-scope cases was run through Method S (no-retrieval LLM baseline) **5 times** in total: the original gate run (outcome = fail, by definition of case acceptance) plus 4 independent re-runs.

A case is **robustly certified** when S fails in ≥ 4/5 runs (difficulty ≥ 0.8).

## Results

| Category | Count | % |
|---|---|---|
| Robustly certified (difficulty ≥ 0.8) | 83 | 92.2% |
| Borderline (difficulty 0.6–0.8) | 0 | 0.0% |
| Too easy (difficulty < 0.6) | 7 | 7.8% |
| **Total** | **90** | 100% |

Average difficulty across all cases: **0.9378**

## By Mode

| Mode | Total | Robust | Borderline | Too Easy |
|---|---|---|---|---|
| skill_guided | 30 | 28 | 0 | 2 |
| skill_adjusted | 20 | 20 | 0 | 0 |
| dynamic | 40 | 35 | 0 | 5 |

## Borderline Cases

None.

## Too-Easy Cases (should be reviewed)

- **sg-11** (skill_guided) difficulty=0.2 — S solved in 4/5 runs
  Prompt: _We need to streamline our product release process by ensuring that whenever we introduce new materials or make engineeri_
- **sg-14** (skill_guided) difficulty=0.2 — S solved in 4/5 runs
  Prompt: _We're launching a new product campaign next quarter and need to evaluate the full impact before we roll it out. Can you _
- **dy-01** (dynamic) difficulty=0.2 — S solved in 4/5 runs
  Prompt: _I need to pull up a recent issue that one of our customers reported last week so I can see what we promised to deliver a_
- **dy-03** (dynamic) difficulty=0.2 — S solved in 4/5 runs
  Prompt: _I need to set up automated safety checks for our engineering change orders and material updates before they go to produc_
- **dy-14** (dynamic) difficulty=0.2 — S solved in 4/5 runs
  Prompt: _We need to record incoming shipments from our suppliers into the system, but I'm not sure if we should be using the invo_
- **dy-30** (dynamic) difficulty=0.2 — S solved in 4/5 runs
  Prompt: _Can you pull up the current status of ticket #12847 and check who our top-performing sales representative is in the Nort_
- **dy-24** (dynamic) difficulty=0.2 — S solved in 4/5 runs
  Prompt: _We need to verify that our current component sourcing meets all regulatory requirements while simultaneously checking ou_
