# Adversarial Ground Truth Construction and Validation

> **Status:** Concept — not yet implemented. Edit freely before implementation begins.
> **Related papers:** Dynabench (Kiela et al., 2021), ANLI (Nie et al., 2020), LLM-as-Judge (Zheng et al., 2023), Evol-Instruct (Xu et al., 2023)
> **Scope for first run:** Dynamic test cases only (25 cases in `test_cases/runtime/dynamic.json`)

---

## 1. Motivation and Scientific Grounding

The benchmark currently has 143 design-time and 85 runtime test cases with manually authored ground truth (single-author, no documented criteria, no validation trail). This is the primary methodological limitation named in Chapter 6.

The adversarial game approach is grounded in established NLP methodology. **Dynabench** (Kiela et al., 2021) introduced human-and-model adversarial loops to generate certified-hard benchmarks. **ANLI** (Nie et al., 2020) applied this to annotation quality. **LLM-as-Judge** (Zheng et al., 2023) established that LLMs can reliably assess benchmark quality. **Evol-Instruct** (Xu et al., 2023) showed that iterative LLM-based prompt mutation produces progressively harder examples.

This work combines these into a three-party adversarial game where **the landscape stays fixed** and only the test case prompt is mutated. The game produces:
1. **Certified-hard cases** — Method A (baseline) fails on them
2. **Documented ground truth** — Judge explains why the correct resource is correct, including a full solution path
3. **Appendix-ready provenance** — every decision is logged and human-readable

---

## 2. The Four Problems Each Case Must Simulate

| Code | Problem | What it looks like |
|---|---|---|
| **P1** | Agent sprawl | Resources from multiple namespaces/vendors could plausibly answer |
| **P2** | Action-space complexity | Multiple resources have overlapping capabilities — disambiguation required |
| **P3** | Semantic specification gap | Prompt vocabulary does not literally appear in any resource descriptor |
| **P4** | Coexistence with established processes | Request maps to or extends a known skill-guided process |

Every accepted case must exercise ≥1 of P1–P4.

---

## 3. Roles and Responsibilities

### 3.1 MUTATOR

**Goal:** Generate a harder variant of the seed prompt that still has the same correct answer.

**Input:**
- `seed_prompt` (str) — the original activity label or user request
- `correct_resource` (dict) — full ORD descriptor of the ground truth resource (ordId, title, shortDescription, capabilities, lineOfBusiness, entityTypes)
- `landscape_summary` (list[dict]) — title + shortDescription + capabilities for all 177 resources
- `mutation_index` (int) — which mutation round (used to escalate difficulty)
- `seed` (int) — random seed for reproducibility across runs

**Output (JSON):**
```json
{
  "mutated_prompt": "...",
  "mutation_strategy": "vocabulary_replacement | context_addition | implicit_dependency | domain_specific_jargon",
  "why_ground_truth_still_correct": "one sentence",
  "vocabulary_overlap_with_descriptor": ["words", "still", "shared"]
}
```

**Mutation strategies (escalating by index):**
- Index 0–2: Vocabulary replacement — paraphrase with synonyms, no shared words with resource descriptor
- Index 3–5: Context addition — add department name, document ID, role, date that increase domain specificity
- Index 6–8: Implicit dependency — state the outcome, not the action (the required resource must be inferred)
- Index 9+: Domain jargon — use technical terms from the business domain that do not appear in any resource descriptor

**Hard constraint:** `vocabulary_overlap_with_descriptor` must shrink with each mutation index. If it reaches 0 and the Mutator cannot go further without changing the ground truth, the seed is marked UNANNOTATABLE.

### 3.2 SOLVER (No-Retrieval Baseline)

**Goal:** Attempt to identify the correct resource by giving an LLM the complete landscape and asking it to pick directly — no embedding, no filtering, no graph traversal. This is the "naive eager catalogue" approach that the thesis identifies as the baseline problem.

**Why No-Retrieval and not Method A:** Method A benefits from embedding similarity and would already beat a purely random baseline. No-Retrieval tests whether a capable LLM with full context can solve the case trivially. If it can, the case is too easy for our benchmark — any retrieval method would also solve it. No-Retrieval is the most permissive possible solver, so failing it is a stronger difficulty certificate.

**Input:** `mutated_prompt` (str), `resources` (list[dict] — all 177 resources, titles + shortDescriptions + capabilities)

**LLM call:** Single chat completion with:
- System: "You are a resource selection assistant. Given a business activity and a list of available resources, identify which single resource best fulfils the activity. Respond with only the ordId."
- User: `Activity: {mutated_prompt}\n\nResources:\n{formatted_resource_list}`

**Output interpretation:**
- `top1_correct = (llm_response == correct_ordId)` → case SOLVED (too easy, mutate further)
- `top1_correct = False` → difficulty boundary reached, pass to Judge
- Record: `top1_returned` (which ordId LLM picked), `correct_in_response` (was correct ordId mentioned at all)

**After the adversarial run:** Method A is also run on all accepted cases as a secondary difficulty check. Cases where Method A also fails are labelled "hard for both" — the most valuable cases for evaluating H3 and H4.

### 3.3 JUDGE

**Goal:** Verify the mutated case is fair, plausible, correctly labelled, and document the full solution path showing why the correct resource is uniquely correct and why the main distractor is wrong.

**Input:**
- `mutated_prompt` (str)
- `correct_resource` (dict) — full ORD descriptor
- `top1_wrong_resource` (dict) — the resource Method A picked (the main distractor)
- `all_resources` (list[dict]) — full landscape for context
- `seed_prompt` (str) — original for reference
- `mutation_strategy` (str)

**Output (JSON) — ALL fields mandatory:**
```json
{
  "plausible": true,
  "reason_plausible": "One sentence: why this reads like a real enterprise request.",

  "ground_truth_correct": true,
  "reason_ground_truth": "One sentence: which specific capability maps to which verb/noun in the prompt.",
  "capability_match": "capability-token → 'exact phrase from prompt'",

  "distractor_analysis": {
    "main_distractor_ordId": "...",
    "why_distractor_is_wrong": "One sentence: which capability the distractor has that superficially matches, and why it is still wrong.",
    "ambiguity_score": 0.41
  },

  "solution_path": {
    "step1": "The prompt asks for X",
    "step2": "X maps to capability Y in the correct resource",
    "step3": "Resource Z (distractor) has capability W which seems related but covers a different action",
    "step4": "No other resource in the landscape has capability Y in this domain",
    "conclusion": "correct_resource is the unique correct answer"
  },

  "fair": true,
  "reason_fair": "One sentence: the correct resource exists and its capabilities are sufficient to fulfil the request.",

  "problems_exercised": ["P2", "P3"],
  "reason_problems": "P2: distractor has overlapping capability. P3: key vocabulary not literal in any descriptor.",

  "difficulty_label": "easy | medium | hard",
  "confidence": 0.88
}
```

**Acceptance criteria — ALL must hold:**
- `plausible = true`
- `ground_truth_correct = true`
- `fair = true`
- `problems_exercised` non-empty
- `distractor_analysis.ambiguity_score ≥ 0.30` (genuine distractor required)
- `confidence ≥ 0.70`

**Ambiguity score definition:**
`ambiguity_score = cosine_sim(embed(prompt), embed(distractor_descriptor)) / cosine_sim(embed(prompt), embed(correct_descriptor))`

Clamped to [0, 1]. A score of 1.0 means distractor and correct are equally similar to the prompt. A score ≥ 0.30 means the distractor is at least 30% as similar as the correct resource — a genuine source of confusion.

---

## 4. Game Loop (per Seed Case)

```
seed_case (prompt + correct_ordId)
  │
  for mutation_index in 0..MAX_MUTATIONS:
    for seed in [42, 137, 999]:   ← 3 independent runs per mutation
      │
      Mutator → mutated_prompt
      Solver  → solved? (top1_correct)
      │
      if solved:   try next mutation_index
      if not:      Judge evaluates
        │
        if accepted: HARVEST → write provenance, break
        if rejected: try next seed
      │
  │
  if no mutation accepted: flag UNANNOTATABLE
  if always solved:        flag TRIVIAL
```

**Harvest rule:** Accept the first mutation_index where at least one seed produces a Judge-accepted case. Among accepted seeds, keep the one with highest Judge confidence.

**MAX_MUTATIONS = 10**, **N_SEEDS = 3** per mutation. Total LLM calls per seed case: at most 10 × 3 × (1 Mutator + 1 Judge) = 60 calls. In practice much fewer since most cases are harvested early.

---

## 5. Ambiguity Requirement

Every accepted case must have a genuine distractor with `ambiguity_score ≥ 0.30`. This is a **fixed threshold, defined before any run**, not tuned post-hoc.

If no resource in the landscape scores ≥ 0.30 for a given case, this is logged as a **landscape coverage gap** — a domain where the landscape lacks sufficient resource overlap to create ambiguity. This is itself a finding: it means that domain is trivially easy for all retrieval methods, and the landscape may need enrichment.

---

## 6. Landscape: Fixed Throughout

The 177 resources in `ord_enriched.json` do not change during the game. Only the prompts are mutated. This ensures:
- Results are comparable to the original benchmark run
- The benchmark tests retrieval quality, not landscape coverage
- Landscape mutations are a separate, future research question

If a seed case cannot be made ambiguous (no distractor ≥ 0.30 threshold), this is logged as a landscape gap, not a test case failure.

---

## 7. Provenance Document per Case

Every accepted case gets a complete evolution log — every participant's output in every round. This is the scientific documentation trail.

File: `test_cases/*/provenance/{case_id}.json`

```json
{
  "case_id": "dy-01",
  "version": "adversarial-v1",
  "seed_prompt": "All users in the building cannot log in to any IT system...",
  "accepted_prompt": "Our entire office authentication infrastructure went down at 08:00...",
  "ground_truth_ordId": "corp.itsm:agent:ITSupportBot:v1",
  "acceptable_alternatives": ["corp.itsm:apiResource:ServiceTicket:v1"],
  "accepted_at": {"mutation_index": 2, "seed": 137},
  "difficulty_certified_by": "no_retrieval",
  "method_A_also_fails": true,
  "ambiguity_score": 0.41,
  "timestamp": "2026-06-05T...",

  "evolution_log": [
    {
      "mutation_index": 0, "seed": 42,
      "mutator_output": {
        "mutated_prompt": "We have a company-wide sign-in outage since early morning. Please open a priority incident ticket.",
        "mutation_strategy": "vocabulary_replacement",
        "why_ground_truth_still_correct": "ITSupportBot handles incident ticket creation for IT outages.",
        "vocabulary_overlap_with_descriptor": ["incident", "IT"]
      },
      "solver_output": {
        "top1_returned": "corp.itsm:agent:ITSupportBot:v1",
        "top1_correct": true
      },
      "judge_output": null,
      "outcome": "SOLVED — mutate further"
    },
    {
      "mutation_index": 2, "seed": 137,
      "mutator_output": {
        "mutated_prompt": "Our entire office authentication infrastructure went down at 08:00 — Kerberos is returning KDC_ERR_C_PRINCIPAL_UNKNOWN.",
        "mutation_strategy": "domain_specific_jargon",
        "why_ground_truth_still_correct": "ITSupportBot handles Kerberos/authentication incidents.",
        "vocabulary_overlap_with_descriptor": []
      },
      "solver_output": {
        "top1_returned": "siemens.plm:agent:AssetManager:v1",
        "top1_correct": false,
        "correct_in_response": false
      },
      "judge_output": {
        "plausible": true,
        "reason_plausible": "Kerberos error codes are realistic enterprise IT jargon.",
        "ground_truth_correct": true,
        "reason_ground_truth": "ITSupportBot has capability incident-management for authentication failures.",
        "capability_match": "incident-management → authentication infrastructure went down",
        "distractor_analysis": {
          "main_distractor_ordId": "siemens.plm:agent:AssetManager:v1",
          "why_distractor_is_wrong": "AssetManager handles physical asset tracking, not Kerberos/IT auth.",
          "ambiguity_score": 0.41
        },
        "solution_path": {
          "step1": "Prompt describes a Kerberos KDC authentication failure",
          "step2": "Kerberos failure is an IT incident requiring triage and escalation",
          "step3": "ITSupportBot has capabilities incident-management and infrastructure-diagnosis",
          "step4": "AssetManager triggered on infrastructure but handles physical, not IT infrastructure",
          "conclusion": "ITSupportBot is the unique correct answer"
        },
        "fair": true,
        "reason_fair": "ITSupportBot exists and its capabilities cover authentication incident response.",
        "problems_exercised": ["P2", "P3"],
        "reason_problems": "P2: AssetManager confusable via infrastructure. P3: Kerberos, KDC_ERR not in any descriptor.",
        "difficulty_label": "hard",
        "confidence": 0.91
      },
      "outcome": "ACCEPTED"
    }
  ]
}
```

The evolution log is the key scientific artefact: every mutation proposed, every Solver response, every Judge decision. It can be directly cited in the appendix.

## 8. Criteria Codebook (fixed before any run)

| # | Criterion | Pass condition |
|---|---|---|
| C1 | Capability alignment | Correct resource has ≥1 capability mapping to the primary verb-noun in prompt |
| C2 | Distractor exists | ≥1 resource has `ambiguity_score ≥ 0.30` |
| C3 | Prompt-only solvability | Correct answer derivable from prompt alone, no process context required |
| C4 | Plausibility | Reads like a realistic enterprise user request |
| C5 | Problem coverage | Exercises ≥1 of P1–P4 |
| C6 | Ground truth stability | Correct resource is still correct after the mutation |
| C7 | Solution path documented | Judge provides step-by-step reasoning including distractor analysis |
| C8 | Judge confidence | ≥ 0.70 |

---

## 9. Human-Readable Appendix Output

The script generates two Markdown files automatically:

### `docs/gt_report_summary.md`
Aggregate statistics table: N seeds attempted, N accepted, acceptance rate, mean mutations to boundary, Judge confidence distribution, P1–P4 distribution, landscape coverage gaps. Ready to paste into the thesis appendix.

### `docs/gt_report_examples.md`
2–3 worked examples rendered as readable prose:
- Original seed prompt
- Accepted mutated prompt  
- Mutation strategy used
- Why the case is non-trivial (which P-problem, why vocabulary does not match)
- Capability match: `capability-token → 'exact phrase in prompt'`
- Distractor analysis: why the wrong resource looks plausible, why it is wrong
- Difficulty certificate: Method A failed at mutation N, distractor ranked above correct resource
- Judge confidence and solution path

---

## 10. Implementation: Files to Create

```
src/adversarial/
  __init__.py
  mutator.py       — Mutator LLM prompt + call, mutation strategy selection
  judge.py         — Judge LLM prompt + structured JSON output parsing
  solver.py        — wrapper: method_a.retrieve() → solved bool + scores
  ambiguity.py     — compute ambiguity_score via embedding cosine
  game.py          — three-party loop, seed management, harvest logic
  report.py        — generate gt_report_summary.md + gt_report_examples.md
  codebook.py      — C1–C8, P1–P4 as Python constants

test_cases/design_time/provenance/   (one JSON per case)
test_cases/runtime/provenance/       (one JSON per case)
docs/gt_report_summary.md            (auto-generated)
docs/gt_report_examples.md           (auto-generated)
```

### Entry point

```bash
python run_adversarial.py \
  --mode design_time \
  --input bpmn \
  --max-mutations 10 \
  --n-seeds 3 \
  --ambiguity-threshold 0.3 \
  --judge-confidence-threshold 0.7
```

---

## 11. Open Questions

- [ ] For runtime cases (dynamic/skill_adjusted): Mutator mutates `user_prompt` only. Should the Judge also re-validate `expected_steps`, or only the step-level `expected_ordIds`?
- [ ] TRIVIAL cases (Solver never fails in 10 mutations): keep as-is with Judge-only validation, or discard?
- [ ] Cross-method validation: after the adversarial run, run Method C on accepted cases to identify the hardest partition (A fails AND C fails)?
- [ ] LLM-generated text detection: run a standard classifier on accepted prompts to verify they pass as natural enterprise language?
