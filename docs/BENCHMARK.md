# Benchmark: Full Evaluation Framework

> **Executive Summary:** Phase 1 complete. Phase 2 complete.
> - **Landscape:** 273 resources across 10 systems · 70/273 ground-truth eligible · 0 near-duplicate pairs
> - **Generation:** LLM Generator → Deterministic Validator (C1 spec check) → LLM Judge (C2–C5) — adversarial construction throughout
> - **Design-Time:** 240 activity cases from 30 process models (15 BPMN + 15 CMMN) · evaluated on Clean-ORD only
> - **Run-Time:** 110 adversarially constructed cases — SG(30) + SA(20) + DY(40) + OOS(20)
> - **Experimental variable:** Clean-ORD vs. Enriched-ORD (capabilities, useCases, processNext, partOfGroups)
> - **Retrieval methods:** A (Embedding) · B (Progressive Disclosure) · C (Graph Walk) · D (Agentic) · E (Filesystem) · S (Baseline-Solver)
> - **Skill Registry** as second semantic layer alongside ORD (Methods B and D)
> - **~350 cases total:** 240 design-time + 110 run-time

---

## Overview

The benchmark is constructed in three phases:

1. **Landscape Phase** — Build a synthetic ORD landscape of 273 resources with controlled similarity structure
2. **Test Case Phase** — Generate adversarial test cases per orchestration mode using a three-party game
3. **Documentation Phase** — Every decision is logged for appendix reference

The key scientific property: **the entire construction process is automated and auditable**. No manual decisions are made without documentation.

**Document structure:**

| Section | Contents |
|---|---|
| **PHASE 1: Landscape Construction** | |
| 1.1 | Systems, ORD fields, entity type vocabulary |
| 1.2 | Custom ambiguity metric — why, how, dimensions |
| 1.2.1 | Similarity tiers, GT-eligibility criterion, tier examples |
| 1.3 | Landscape generation — seeds, iterative gap-filling, near-duplicate reduction |
| 1.5 | Landscape results — 273 resources, composition table, audit trail |
| **PHASE 2: Test Case Construction** | |
| 2.1 | Design-Time evaluation — process models, SKILL.md, enrichment, 240 cases |
| 2.1.1 | The two ORD states (Clean vs. Enriched) |
| 2.1.2 | Process model construction (`generate_processes.py`) |
| 2.1.3 | SKILL.md construction (`generate_skills.py`) |
| 2.1.4 | ORD enrichment (`enrich_from_processes.py`) |
| 2.1.5 | Test case extraction (`extract_cases.py`) |
| 2.1.6 | Evaluation — P@1, R@5, MRR |
| 2.2 | Run-Time evaluation — 110 adversarial cases, 6 methods × 2 ORD states |
| 2.2.1 | Query taxonomy — enterprise motivation, 5 classes, 110 cases |
| 2.2.2 | Test case generation — adversarial loop, per-mode construction |
| 2.2.3 | Evaluation — primary metric per mode (Routing/Gap-Detection/Top-1/Refusal) |
| **Appendix** | |
| Implementation Decisions | Deviations and refinements made during actual construction |
| Methodological Limitations | Self-preference bias, solver gate, equal weighting, OOS risk |
| Design Note | Single-candidate vs. ranked retrieval in Methods D, E, S |

---

## PHASE 1: Landscape Construction

**Goal:** Generate synthetic retrieval resources across 10 active systems, all valid per ORD v1.16 spec, with controlled similarity structure.

**Target distribution per system (API dominated architectures):**
- ~50% apiResource
- ~25% agent
- ~25% dataProduct


### 1.1 Initial Landscape Setup

**Systems (namespace → domain):**

| Namespace | Domain |
|---|---|
| `sap.s4` | ERP, Finance, Manufacturing — SAP S/4HANA |
| `sap.sf` | HR and People — SAP SuccessFactors |
| `sap.ariba` | Procurement — SAP Ariba |
| `sap.crm` | Sales and Customer — SAP CRM |
| `sap.ehs` | Safety and Environment — SAP EHS |
| `corp.itsm` | IT Service Management — Corporate ITSM |
| `my.mes` | Manufacturing Execution — Custom MES |
| `workday.hcm` | HR (non-SAP) — Workday HCM |
| `emarsys.cx` | Marketing and CX — Emarsys |
| `siemens.plm` | Product Lifecycle — Siemens PLM |
| `sap.odm` | Entity Taxonomy only — 50 shared business object labels, no retrieval resources |

**Entity Types:**
All 10 systems share a single entity type vocabulary: `sap.odm`. There is no separate per-vendor namespace. A Workday resource referencing `sap.odm:entityType:Employee:v1` is correct and expected — this shared vocabulary is what creates cross-system similarity connections in the benchmark. The entity types are derived from the SAP One Domain Model (sap.odm), a real SAP standard for cross-domain business objects.

**50 entity types across 10 systems:**

| Business Object | Primary Systems | Also appears in |
|---|---|---|
| Employee, WorkforcePerson, Payroll, Benefit, PerformanceReview, TimeOff, Compensation | sap.sf, workday.hcm | sap.s4 (payroll integration) |
| Vendor, PurchaseOrder, PurchaseRequisition, Invoice, Contract, ExpenseReport | sap.ariba | sap.s4, sap.ehs (supplier compliance) |
| CostCenter, Account, Budget | sap.s4 | sap.ariba, corp.itsm |
| Supplier, Approval | sap.ariba, sap.s4 | siemens.plm, sap.ehs, corp.itsm, sap.sf |
| CustomerOrder, CustomerAccount, Customer, SalesOpportunity | sap.crm | sap.s4 |
| CustomerJourney, CustomerSegment, Campaign | emarsys.cx | sap.crm |
| Machine, ProductionOrder, MaintenanceOrder, WorkOrder, IoTSensorStream, QualityInspection | my.mes | sap.s4 |
| Material, Location | sap.s4, my.mes | siemens.plm, sap.ariba |
| ProductItem, EngineeringChange | siemens.plm | sap.s4 |
| SafetyIncident, Incident, Substance, HazardousSubstance | sap.ehs | sap.s4 |
| ServiceTicket, ITEquipment, Asset, SoftwareLicense, ChangeRequest | corp.itsm | sap.s4, sap.sf |
| Project, Document, Task, Report, Notification, Compliance | all systems | — |

**Required fields per resource type** (from `benchmark/landscape/ord_spec_rules.json`):

```
agent:       ordId, title, shortDescription, version, partOfPackage, visibility, releaseStatus
apiResource: ordId, title, shortDescription, version, partOfPackage, visibility, releaseStatus,
             apiProtocol, resourceDefinitions (each: type, mediaType, url, accessStrategies)
dataProduct: ordId, title, shortDescription, version, partOfPackage, visibility, releaseStatus,
             type (primary|derived), category (business-object|analytical|operational|other),
             outputPorts (list of {ordId})
entityType:  ordId, localId, level (aggregate|sub-entity), title, shortDescription,
             version, partOfPackage, visibility, releaseStatus
package:     ordId, title, shortDescription, version, vendor
```

**Additional semantic fields** (used in ambiguity scoring — validator issues warnings if absent):

```
agent:       relatedEntityTypes, lineOfBusiness, tags, industry
apiResource: exposedEntityTypes, lineOfBusiness, tags, industry
dataProduct: entityTypes, lineOfBusiness, tags, industry
```

EntityType references use different field names per resource type:
- `agent` → `relatedEntityTypes` (array of strings)
- `apiResource` → `exposedEntityTypes` (array of `{ordId}`)
- `dataProduct` → `entityTypes` (array of strings)

---

### 1.2 Ambiguity Metric

Measures structural similarity between any two ORD resources using only fields defined in the ORD v1.16 spec. Fully deterministic — no LLM, no external embeddings. 

**Why an ambiguity metric?**
The goal of phase 1 is to generate a realistic enterprise system landscape with ambiguity between resoures and semantically overlapping descriptions. Therefore an ambiguity metric is necessary to measure similarity between resources during generation. But there is no existing similarity measure that is directly applicable to ORD resources. The basic options are:

- **Embedding cosine similarity** (e.g. Sentence-BERT): produces a scalar but is uninterpretable — it cannot say *why* two resources are similar, and it carries training-data biases that do not reflect enterprise metadata structure. Most importantly, it cannot be used to *construct* ambiguity: to build a HIGH-tier pair you need to know which fields to set, not just that the pair should score 0.7.
- **BM25 / keyword overlap**: only captures text, ignores the structural fields that define what a resource *is* in ORD (entity types, lineOfBusiness, resource type).

To solve this a **custom metric** was designed. This metric uses semantic fields that ORD v1.16 defines and that allow developers to describe what a resource does and which business objects it operates on. Equal weighting is a deliberate choice: there is no empirical basis to weight `lineOfBusiness` over `tags` without a labelled dataset of human confusion judgements, which does not exist for ORD resources. The two adjustments (cross-namespace bonus, type penalty) are theoretically motivated by the retrieval problems the thesis addresses (P1, P2) rather than tuned from data.

This makes the metric **transparent** (every score has a field-level breakdown), **controllable** (HIGH/MEDIUM/LOW pairs can be constructed by design), and **reproducible** (deterministic, no model weights).

**Six equal-weight dimensions plus two adjustments:**

| # | Dimension | Field | Method | Why it matters |
|---|---|---|---|---|
| 1 | Text | `title + shortDescription + description` | TF-IDF cosine — all text is tokenised; each term weighted by how rare it is across all resources (inverse document frequency); cosine similarity between the two term vectors | Captures what the resource does in natural language; rare domain-specific terms ("hazardous", "accrual") count more than generic words like "management" or "data" |
| 2 | Business Objects | `relatedEntityTypes` / `exposedEntityTypes` / `entityTypes` | IDF-weighted Jaccard — intersection / union of entity type sets, with each type weighted by its rarity across all resources | The business objects a resource operates on are the strongest structural signal — two resources sharing `Employee:v1` are semantically related regardless of description |
| 3 | Domain | `lineOfBusiness` | Jaccard — intersection / union of LoB string sets | The functional domain (HR, Finance, Manufacturing…) — resources in the same domain are inherently more confusable than across unrelated domains |
| 4 | Keywords | `tags` | Jaccard — intersection / union of tag string sets | Developer-assigned keywords surface intent not always visible in the description (e.g. "approval-workflow", "compliance") |
| 5 | Industry | `industry` | Jaccard — intersection / union of industry string sets | Sector (Retail, Financial Services…) — rarely filled but contributes when present |
| 6 | Local ID | third segment of `ordId` (CamelCase tokenized) | Jaccard — CamelCase split into tokens, then intersection / union | Structural identity independent of description; `RecruiterAssistant` and `TimeOffAssistant` share `Assistant` even if descriptions diverge |
| + | Cross-namespace bonus | +0.5 to numerator before /6 | Added as raw value before normalisation — not a dimension score | Models P1 (Agent Sprawl): a user asking for an HR agent does not know whether to look in sap.sf or workday.hcm. Cross-namespace pairs are structurally more ambiguous because no system-context signal is available. The +0.5 is equivalent to ~3 fully-matching dimensions |
| × | Type penalty | ×0.5 after normalisation if types differ | Multiplied after the full score is computed | A user asking for an action will not pick a data product. The ×0.5 halves rather than zeros the score because type-unaware methods (embedding cosine) can still confuse cross-type resources |

**Formula:**
```
raw    = (text + localId + entityTypes + lineOfBusiness + tags + industry + 0.5_if_cross_ns) / 6
final  = raw × 0.5   if type(A) ≠ type(B)
       = raw          otherwise
```

Missing fields contribute 0.0. The cross-namespace bonus is added before dividing by 6, making cross-vendor same-domain pairs noticeably more ambiguous (models P1).

**Implementation:** `src/adversarial/preselect.py` → `compute_landscape_ambiguity()`

**Run:** `python3 benchmark/ambiguity/run_ambiguity.py`

---

#### 1.2.1 Similarity Tiers and Targets

The ambiguity metric exists to give us control over the landscape during generation. The goal is a benchmark where retrieval is genuinely non-trivial: every GT-eligible resource must have real competitors that an orchestrator could plausibly confuse it with. Without controlled similarity structure, a randomly generated landscape would consist mostly of completely unrelated resources — correct retrieval would be trivially easy and the benchmark would not measure anything scientifically useful.

**Similarity tiers — thresholds and purpose:**

The thresholds were determined empirically by validating that resources at each tier boundary match the intended semantic relationship. The tier examples below — drawn directly from the benchmark landscape — confirm that each threshold separates meaningfully different levels of confusability.

| Tier | Threshold | Purpose | GT target |
|---|---|---|---|
| **HIGH** | 0.50–0.75 | Genuine distractors — identical ET + LoB across namespaces; stress-test retrieval. Upper bound 0.75: above this are near-duplicates removed in Step 3. | ≥3 neighbors |
| **MEDIUM** | 0.25–0.50 | Pool of "almost right" distractors distinguishable with enrichment context (capabilities, useCases). | ≥5 neighbors |
| **LOW** | 0.10–0.25 | Structural context for graph-based methods (Method C); fills automatically as landscape grows. | ≥5 neighbors |
| **Background** | < 0.10 | Structurally unrelated (76.6% of all pairs). No retrieval confusion expected. | — |

Only resources that satisfy the **GT-eligibility criterion** (H≥3 · M≥5 · L≥5) are used as ground-truth targets in the Phase 2 test cases. This criterion ensures that every evaluation target has a designed neighborhood of genuine distractors at all three confusability levels — a prerequisite for evaluating the three core problems (P1 Agent Sprawl, P2 Vocabulary Drift, P3 Context Sensitivity). Resources that fail this criterion are still part of the landscape (as non-GT steps in process models) but are not used as retrieval targets because their neighborhood would make the evaluation trivially easy or structurally underspecified. The thresholds H≥3, M≥5, L≥5 were defined to be achievable through generation while guaranteeing a competitive neighborhood.

**Note on fast_sim vs. full sim:** During generation, similarity is computed without TF-IDF (`fast_sim`, text=0). The full similarity including TF-IDF is typically +0.05 to +0.15 higher, because LLM-generated descriptions for structurally similar resources share vocabulary. The tiers and thresholds defined here refer to **full similarity** (including TF-IDF), which is the scientifically relevant score. `fast_sim` is used only as an efficient proxy during construction — it is always a lower bound, so if `fast_sim` confirms a tier, the full sim will too.

**Near-duplicate threshold (fast_sim ≥ 0.75):** Resources scoring above this during generation are rejected automatically. After generation, `reduce_near_dups.py` scanned for all pairs with full_sim ≥ 0.75. For each pair: if one resource already has ≥3 HIGH neighbors (i.e. the GT-eligibility minimum is already met), it is removed without loss — the neighbor count is sufficient. Otherwise the resource is rewritten via LLM to lower text similarity below 0.75. After cleanup the landscape contains no pair with full_sim ≥ 0.75. Any remaining pairs at 0.50–0.74 serve as HIGH-tier distractors. `near_dup_pairs.json` documents all resolved pairs and is used as an exclusion list during test case selection (both members of a pair cannot be ground-truth in the same test case).

**Tier examples from the benchmark landscape** — each example validates that the threshold boundary corresponds to the intended semantic relationship:

<details>
<summary><strong>HIGH (sim = 0.74)</strong> — campaign analytics across two CX systems</summary>

| | Resource A | Resource B |
|---|---|---|
| **ordId** | `emarsys.cx:dataProduct:CampaignPerformanceAnalytics:v1` | `sap.crm:dataProduct:CampaignSegmentationAndROIAnalytics:v1` |
| **title** | Campaign Performance Analytics Data Product | Campaign Segmentation and ROI Analytics |
| **system** | emarsys.cx | sap.crm |
| **entityTypes** | Campaign, CustomerSegment, CustomerAccount | Campaign, CustomerAccount, CustomerSegment |
| **lineOfBusiness** | Marketing and CX | Marketing and CX |
| **score breakdown** | text=0.44 · ET=1.00 · LoB=1.00 · tags=1.00 · cross-ns=+0.5 | → **sim=0.74** |

Link: https://pages.github.tools.sap/I750252/MasterThesis/landscape/emarsys.cx/emarsys-cx-dataProduct-CampaignPerformanceAnalytics-v1/

Identical entity types and LoB make them structurally indistinguishable without system-context. A request for "campaign ROI analytics" could match either equally well.
</details>

<details>
<summary><strong>MEDIUM (sim = 0.50)</strong> — sales capacity across CRM and HR systems</summary>

| | Resource A | Resource B |
|---|---|---|
| **ordId** | `sap.crm:apiResource:SalesTeamAvailabilityAndCapacityService:v1` | `workday.hcm:apiResource:TimeOffAndCapacityAllocationManagement:v1` |
| **title** | Sales Team Availability and Capacity Service | Employee Absence and Resource Utilization API |
| **system** | sap.crm | workday.hcm |
| **entityTypes** | Employee, TimeOff | Employee, TimeOff |
| **lineOfBusiness** | Sales | Sales |
| **score breakdown** | text=0.38 · ET=1.00 · LoB=1.00 · tags=0.00 · cross-ns=+0.5 | → **sim=0.50** |

Link: https://pages.github.tools.sap/I750252/MasterThesis/landscape/sap.crm/sap-crm-apiResource-SalesTeamAvailabilityAndCapacityService-v1/

Same entity types and shared LoB, different systems (CRM vs. HR). Distinguishable with domain context — CRM manages availability for sales operations, HR exposes the underlying leave data.
</details>

<details>
<summary><strong>LOW (sim = 0.25)</strong> — vendor data across ITSM and manufacturing</summary>

| | Resource A | Resource B |
|---|---|---|
| **ordId** | `corp.itsm:apiResource:ProcurementVendorManagementAPI:v1` | `my.mes:apiResource:MaterialAndVendorMasterData:v1` |
| **title** | Procurement Vendor Management API | Material and Vendor Master Data API |
| **system** | corp.itsm | my.mes |
| **entityTypes** | PurchaseOrder, Vendor | Material, Vendor |
| **lineOfBusiness** | Operations | Product Lifecycle Management |
| **score breakdown** | text=0.31 · ET=0.32 · LoB=0.00 · tags=0.20 · cross-ns=+0.5 | → **sim=0.25** |

Link: https://pages.github.tools.sap/I750252/MasterThesis/landscape/corp.itsm/corp-itsm-apiResource-ProcurementVendorManagementAPI-v1/

Only one shared entity type (Vendor), different LoB. Structurally connected but functionally distinct — ITSM procurement vs. manufacturing master data.
</details>


---

### 1.3 Landscape Generation

The landscape was generated in three sequential steps. The overall goal was to build a resource landscape where GT-eligible resources have designed neighborhoods that create realistic retrieval challenges. A fully random landscape would not achieve this — without targeted gap-filling, most resources would be structurally unrelated and retrieval would be trivially easy.

**Why automated generation?** Manual curation of 273 enterprise API/agent/data-product descriptions across 10 systems would be impractical and introduce subjective bias. LLM generation with deterministic validation ensures every resource is realistic, spec-compliant, and structurally placed where the benchmark needs it.

**Validation and judge gate** — applied after every Generator output across all three steps:

Every generated resource passes through a two-stage gate before being accepted. The deterministic validator runs first at zero LLM cost; the LLM Judge only runs if the spec check passes. This ordering minimises token cost: structurally invalid resources (wrong fields, bad ordId pattern) are caught immediately without an LLM call.

| Criterion | Who checks | Cost on failure |
|---|---|---|
| C1: ORD spec compliance | `validate_ord.py` (deterministic) | Zero LLM calls — immediate return |
| C2: Coherent with system domain | LLM Judge | Only if C1 passes |
| C3: Not a duplicate | LLM Judge | Only if C1–C2 pass |
| C4: EntityType references semantically justified | LLM Judge | Only if C1–C3 pass |
| C5: Description still makes domain sense | LLM Judge | Only if C1–C4 pass |

---

**Step 1 — Seed generation** (`generate_seeds.py`)

30 seed resources — 3 per system (1 agent, 1 apiResource, 1 dataProduct) — provide the starting population for iterative generation. Starting with diverse types per system ensures the type distribution target (50% API / 25% agent / 25% DP) is seeded correctly from the beginning. Entity types are assigned explicitly via `ENTITY_TYPES_BY_DOMAIN`, ensuring all 50 sap.odm types are referenced by at least one seed — a requirement for Method C (graph walk), which uses entity type IDs as traversal entry points. Each seed goes through Generator → C1 → Judge.

---

**Step 2 — Iterative gap-filling** (`generate_iterative.py`)

Starting from the 30 seeds, new resources are generated round by round until the landscape reaches 300 resources (30 per system, 50/25/25 distribution). The process has a natural bootstrap structure: early rounds primarily fill the gaps of the 30 seeds (each seed has an empty tier neighborhood initially), while later rounds fill the gaps of newly generated resources. Every accepted resource immediately updates the `tier_counts_map` — it may satisfy HIGH/MEDIUM gaps for existing resources before those gaps are explicitly processed in the same round. This means the landscape becomes progressively denser: resources generated to fill a gap for resource A simultaneously reduce the gaps for resources B, C that share the same entity types or LoB.

Each round fills HIGH gaps before MEDIUM — this is deliberate: HIGH-fill resources (same ET + same LoB + cross-namespace) often satisfy MEDIUM slots for other resources simultaneously. Processing HIGH first maximises shared coverage and reduces total LLM calls.

Similarity is computed without TF-IDF during generation (structural dimensions only: entityTypes, lineOfBusiness, tags, localId — all O(1) Jaccard, called `fast_sim`). TF-IDF is only used in the final ambiguity report. This makes generation fast: no expensive recomputation after each new resource.

A **pre-check** before each LLM call builds a dummy resource with the target structural profile and computes `fast_sim` deterministically. If no profile reaches the required tier, the gap is skipped without an LLM call. This eliminates the majority of wrong-tier failures before they cost tokens.

Per-round algorithm:
```
PERSISTENT tier_counts_map: {ordId → {high, medium, low}}  — updated incrementally

EACH ROUND:
  1. Compute gaps: resources with high<3 or medium<5
     → sorted HIGH-all-first, MEDIUM-all-second
  2. For each gap (target_ordId, tier):
       PRE-CHECK: build dummy profile, verify fast_sim in tier → skip if not reachable
       GENERATOR: prompt includes system domain, rtype, confirmed ET IDs, LoB
                  ET + LoB enforced deterministically after LLM call
       SOLVER:    fast_sim(target, generated) in tier? → proceed
       JUDGE:     C1 deterministic → C2–C5 LLM
       ACCEPT → save, update tier_counts_map, log to enrichment_log.json
  3. Stop when 300 resources OR no gaps remain
```

LOW tier is not actively generated — it fills automatically as the landscape grows (any resource in 0.10–0.25 range counts).

Every action is logged to `benchmark/landscape/logs/enrichment_log.json` with phase, round, outcome, profile, achieved_sim, judge_verdict, and token counts.

---

**Step 3 — Near-duplicate reduction** (`reduce_near_dups.py`)

After generation, a full TF-IDF scan identifies all pairs with full_sim ≥ 0.75. For each such pair: if one resource already satisfies H≥3 (the minimum is met, removal causes no loss), it is removed. Otherwise the resource is rewritten via LLM to lower text similarity below 0.75. This step is necessary because LLM-generated descriptions for structurally similar resources tend to share vocabulary, pushing full_sim above 0.75 even when `fast_sim` was below during generation (TF-IDF adds +0.05–0.15 on average).

---

### 1.4 Landscape Results

**Final landscape statistics (full TF-IDF, 273 resources):**
- 70/273 (26%) satisfy all three tier targets — ground-truth eligible for test cases
- HIGH satisfied (≥3): 81/273 · MEDIUM (≥5): 230/273 · LOW (≥5): 272/273
- 0 pairs with full_sim ≥ 0.75 — near-duplicate free

70 ground-truth eligible resources are sufficient for 30 test cases per mode across 4 modes. Partially satisfied resources serve as distractors.

**Final landscape composition (273 resources after near-duplicate reduction):**

| System | API | Agent | DP | Total | GT-eligible |
|---|---|---|---|---|---|
| sap.s4 | 14 | 6 | 8 | 28 | 10 |
| sap.sf | 15 | 6 | 5 | 26 | 4 |
| sap.ariba | 13 | 3 | 7 | 23 | 7 |
| sap.crm | 11 | 7 | 9 | 27 | 7 |
| sap.ehs | 15 | 6 | 9 | 30 | 4 |
| corp.itsm | 14 | 8 | 7 | 29 | 9 |
| my.mes | 15 | 5 | 9 | 29 | 9 |
| workday.hcm | 13 | 9 | 4 | 26 | 6 |
| emarsys.cx | 13 | 8 | 8 | 29 | 8 |
| siemens.plm | 14 | 8 | 4 | 26 | 6 |
| **TOTAL** | **137 (50%)** | **66 (24%)** | **70 (26%)** | **273** | **70 (26%)** |

GT-eligible = satisfies HIGH≥3 · MEDIUM≥5 · LOW≥5 (full TF-IDF). 70 resources across all 10 systems usable as ground-truth.

**Logs and traces:**



Sample log entry (`enrichment_log.json`) — iterative generation, HIGH tier accepted:

```json
{
  "phase": "iterative",
  "round": 1,
  "action": "create",
  "outcome": "accepted",
  "target_resource": "emarsys.cx:apiResource:JourneyContactStateAPI:v1",
  "tier_target": "high",
  "tier_actual": "high",
  "achieved_sim": 0.5833,
  "profile": {
    "et_ids": ["sap.odm:entityType:Campaign:v1", "sap.odm:entityType:CustomerAccount:v1"],
    "lob": ["Marketing and Customer Experience"],
    "rtype": "apiResource",
    "namespace": "sap.crm"
  },
  "solver_breakdown": {
    "text": 0.0, "localId": 0.0, "entityTypes": 1.0,
    "lineOfBusiness": 1.0, "tags": 0.25, "cross_namespace_bonus_applied": true
  },
  "judge_verdict": {
    "c2_coherent": true, "c3_not_duplicate": true,
    "c4_et_justified": true, "accepted": true
  },
  "generator_tokens": 1243,
  "judge_tokens": 1102
}
```

The `target_resource` is the existing resource the new resource was generated to fill a HIGH gap for. `achieved_sim` is the fast_sim score (no TF-IDF); full TF-IDF would be slightly higher. The `solver_breakdown` shows which dimensions contributed to the similarity score.

| Artefact | Location | Contents |
|---|---|---|
| Generation log | `benchmark/landscape/logs/enrichment_log.json` | Every seed/iterative/dedup action: phase, round, outcome, profile, achieved_sim, judge_verdict, tokens |
| Near-dup pairs | `benchmark/landscape/logs/near_dup_pairs.json` | All resolved pairs with full_sim ≥ 0.75 |
| Web explorer | `/audit/` → Landscape tab | Filterable table of accepted/rejected resources with judge responses |

---

## PHASE 2: Test Case Construction & Experimental Design

The thesis proves that **semantic ORD metadata enrichment improves retrieval quality** in enterprise agent orchestration. Two evaluation dimensions answer this from different angles:

```
BPMN/CMMN process model
  ↓ (Design-Time construction)
  ├──→ All 8 steps → Activity Cases (240)      ← Design-Time evaluation input
  └──→ GT steps only:
        ├──→ ord_enriched.json                  ← Run-Time: Enriched-ORD state
        └──→ skills/{id}.md (SKILL.md)          ← Run-Time: Skill Registry

         ↓                              ↓
  2.1 Design-Time                2.2 Run-Time
  Activity → Resource            User Query → Resources
  Clean-ORD only                 Clean-ORD vs. Enriched-ORD
  (no enrichment used)           (Δ measures enrichment value)
```

The process models are the shared construction artefact: they generate activity cases for Design-Time evaluation *and* produce enrichment fields for Run-Time. Design-Time evaluates on Clean-ORD only — the enrichment is not used there.

---

### 2.1 Design-Time Evaluation

**Question:** Given a process model activity description (BPMN or CMMN), can each retrieval method correctly identify the ORD resource that executes this activity — using only Clean-ORD metadata?

This evaluation addresses the core problem from Semantic BPM research: process models describe *what* needs to happen (activities), but not *which* system capability executes each step. The design-time question is whether ORD metadata alone — without process context — is sufficient to bridge this gap.

---

#### 2.1.1 The Two ORD States

**Clean-ORD** (`ord.json`, current 273-resource landscape):
Mandatory ORD v1.16 fields only: ordId, title, shortDescription, description, entityTypes, lineOfBusiness, tags, industry.

**Enriched-ORD** (`ord_enriched.json`, same 273 resources + process-derived fields):

| Field | Source | How generated |
|---|---|---|
| `capabilities` | Process step labels | Verb-noun tokens ("diagnose-equipment", "approve-expense") |
| `useCases` | Process step descriptions | 2–3 sentence user-facing context per step |
| `processNext` | Process sequence flows | ordIds of the resource used in the next step |
| `partOfGroups` | Process identity | {groupId: process_name, groupTypeId: "bpmn" or "cmmn"} |

Only GT-eligible resources appearing in a process step receive enrichment fields. Non-GT resources and GT resources not covered by any process remain at Clean-ORD level.

---

#### 2.1.2 Process Model Construction (`generate_processes.py`)

Before test cases can be extracted, 30 BPMN/CMMN process models must be built through a controlled adversarial game. A free LLM output without validation would produce structurally invalid processes or semantically inconsistent activity-resource mappings.

**Resource selection (deterministic — no LLM):**
```
Select exactly 8 resources per process model:
  4 × GT-eligible resources (H≥3, M≥5, L≥5)
  4 × non-GT resources
  Constraint: span ≥3 namespaces, ≥1 agent + ≥1 apiResource
  Coverage-aware: prefer GT resources not yet in any prior model
  (30 models × 4 GT-slots = 120 slots ≥ 70 GT resources → full coverage guaranteed)
```

The 4/4 split is deliberate: GT-eligible resources have genuine HIGH-tier distractors, making design-time retrieval non-trivial. Non-GT resources fill steps that need no strong distractor — they are easier to retrieve but necessary for a coherent process scenario.

**Adversarial game:**
```
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  RESOURCE SELECTION  │────▶│    GENERATOR (LLM)   │────▶│ VALIDATOR (script│────▶│   JUDGE (LLM)    │
│  4 GT + 4 non-GT     │     │  process model       │     │ V1–V6, zero LLM  │     │  J1–J6 quality   │
│  (deterministic)     │     │  + enrichment fields │     │ cost on failure) │     │  checks          │
└──────────────────────┘     └──────────────────────┘     └──────────────────┘     └──────────────────┘
                                      ↑   │ fail                  │ fail                   │ accepts
                                      └───┘◀──────────────────────┘                        ↓
                                                                              ord_enriched.json updated
                                                                              → process_construction_log.json
```

**Generator output — two parts in one call:**

*Part 1: Process model*
```xml
<process id="proc_machine_breakdown_v2" type="bpmn">
  <step id="s1" label="Diagnose equipment failure"
        description="Identify root cause using sensor data"
        ordId="my.mes:apiResource:EquipmentOEEAnalytics:v1"
        capability="diagnose-equipment"
        useCase="Identify the root cause of unplanned equipment downtime"/>
  <step id="s2" .../>
  <sequenceFlow from="s1" to="s2"/>
</process>
```

*Part 2: Enrichment fields (GT-eligible resources only)*
```json
{
  "my.mes:apiResource:EquipmentOEEAnalytics:v1": {
    "capabilities": ["diagnose-equipment"],
    "useCases": ["Identify the root cause of unplanned equipment downtime"],
    "processNext": ["my.mes:agent:ProductionScheduleOptimizer:v1"],
    "partOfGroups": [{"groupId": "proc_machine_breakdown_v2", "groupTypeId": "bpmn"}]
  }
}
```

**Validator (deterministic — V1–V6, zero LLM cost on failure):**

| Check | Rule |
|---|---|
| V1: ordId existence | All step ordIds exist in 273-resource landscape |
| V2: uniqueness | No ordId appears twice in the same process |
| V3: 4/4 constraint | Exactly 4 GT-eligible + 4 non-GT resources |
| V4: namespace spread | Steps span ≥3 different namespaces |
| V5: type variety | At least 1 agent + 1 apiResource |
| V6: step count | Exactly 8 steps |

**Judge (LLM — J1–J6):**

| Check | Criterion |
|---|---|
| J1 | Process type correct: BPMN = structured/sequential; CMMN = case-driven/conditional |
| J2 | Activity labels are business activities, not technical resource descriptions |
| J3 | Activity descriptions state the business need, not the resource name or type |
| J4 | Resource assigned to each step is semantically correct for that activity |
| J5 | Process tells a coherent enterprise story |
| J6 | Enrichment fields are semantically correct: capabilities match step action, useCases describe real user context, processNext reflects actual sequence |

**Log entry (`process_construction_log.json`)** —  · browsable at `/audit/` → Design-Time tab:
```json
{
  "process_id": "proc_machine_breakdown_v2",
  "attempt": 1,
  "resource_pool": {"gt": ["ordId1", "ordId2", "ordId3", "ordId4"],
                    "non_gt": ["ordId5", "ordId6", "ordId7", "ordId8"]},
  "process_type": "bpmn",
  "validator_results": {"V1": true, "V2": true, "V3": false, "V4": "skipped", "V5": "skipped", "V6": "skipped"},
  "validator_failure": "V3: 3 GT + 5 non-GT, need exactly 4/4",
  "judge_results": null,
  "judge_response": null,
  "outcome": "VALIDATOR_FAIL"
}
```

---

#### 2.1.3 SKILL.md Construction (`generate_skills.py`)

Each accepted process model immediately triggers SKILL.md generation. The SKILL.md is generated from the same process XML — the Generator in 2.1.2 already produced all the content needed (step labels, descriptions, ordIds). The Generator writes the SKILL.md directly as part of its output; no separate LLM call is needed.

**Example — same process model as 2.1.2, now as SKILL.md:**
```yaml
---
name: proc-machine-breakdown-v2
description: >
  End-to-end orchestration for unplanned equipment failure on the shop floor.
  Covers diagnosis, maintenance scheduling, and production rescheduling.
metadata:
  process-id: proc_machine_breakdown_v2
  process-type: bpmn
  landscape-version: v2-benchmark-273
---

## Steps

### Step 1: Diagnose equipment failure
<!-- ord_confirmed: my.mes:apiResource:EquipmentOEEAnalytics:v1 -->
**Input:** equipment_id, failure_timestamp
**Output:** root_cause_report
**Capability:** diagnose-equipment
Retrieve OEE data and sensor streams to identify the root cause of the failure.

### Step 2: Schedule maintenance crew
<!-- ord_confirmed: my.mes:agent:ProductionScheduleOptimizer:v1 -->
**Input:** root_cause_report, affected_components
**Output:** maintenance_schedule
**Capability:** schedule-maintenance
Trigger automated scheduling to assign the correct maintenance team and time slot.
```

The `ord_confirmed` annotation per step is the link to the benchmark landscape — it is what Methods B and D use via `describe_skill()`.

**Validator (deterministic — S1–S4):**

| Check | Rule |
|---|---|
| S1 | Every step has exactly one `ord_confirmed` ordId |
| S2 | All `ord_confirmed` ordIds exist in 273-resource landscape |
| S3 | No ordId appears in `ord_confirmed` more than once in the same skill |
| S4 | Step descriptions mention the business activity, NOT the resource name or ordId |

**Judge (LLM — SQ1–SQ3):**

| Check | Criterion |
|---|---|
| SQ1 | Input/Output for each step is plausible in a real enterprise workflow |
| SQ2 | Step descriptions are in user-facing language (not "this agent monitors...") |
| SQ3 | Skill description clearly states what scenario it covers and its boundaries |

Log: `skill_construction_log.json` — same schema as process log.

---

#### 2.1.4 ORD Enrichment (`enrich_from_processes.py`)

The enrichment fields are extracted directly from the accepted process model — no additional LLM call needed. For each GT-eligible step, the process XML already contains `capability` and `useCase` attributes (written by the Generator in 2.1.2). The script reads these and writes them to `ord_enriched.json`.

```
For each process step where resource is GT-eligible:
  capabilities ← verb-noun tokens from step label
  useCases     ← step description in user-facing language
  processNext  ← ordId of the next GT-eligible step's resource
  partOfGroups ← [{groupId: proc_name, groupTypeId: "bpmn"|"cmmn"}]

Non-GT steps are skipped — no enrichment fields written for non-GT resources.
Write to: ord_enriched.json (same 273 resources, GT-step fields added)
```

**Example — from process step to enriched resource:**

Process step (from 2.1.2 Generator output):
```xml
<step id="s1" label="Diagnose equipment failure"
      description="Identify root cause using sensor data"
      ordId="my.mes:apiResource:EquipmentOEEAnalytics:v1"
      capability="diagnose-equipment"
      useCase="Identify the root cause of unplanned equipment downtime"/>
<step id="s2" label="Schedule maintenance crew"
      ordId="my.mes:agent:ProductionScheduleOptimizer:v1" .../>
```

Resulting `ord_enriched.json` entry for `EquipmentOEEAnalytics:v1`:
```json
{
  "ordId": "my.mes:apiResource:EquipmentOEEAnalytics:v1",
  "title": "Equipment OEE Analytics",
  "shortDescription": "...",
  "capabilities": ["diagnose-equipment"],
  "useCases": ["Identify the root cause of unplanned equipment downtime"],
  "processNext": ["my.mes:agent:ProductionScheduleOptimizer:v1"],
  "partOfGroups": [{"groupId": "proc_machine_breakdown_v2", "groupTypeId": "bpmn"}]
}
```

Script: `benchmark/test_cases/enrich_from_processes.py`

---

#### 2.1.5 Test Case Extraction (`extract_cases.py`)

Test cases are extracted deterministically from all 30 accepted process models — no adversarial game needed. Each process step becomes exactly one design-time retrieval case.

The input label includes the process title as context prefix (implemented in `dt_cases.py` via `ENTITY_TYPES_BY_DOMAIN`). This reflects the realistic scenario: an orchestrator executing a process knows which process it is running. The process title grounds the activity in its domain and helps methods that use the label for namespace or entity-type routing. Further metadata could be used.

**Example — from process step to test case:**

Process step:
```xml
<step id="s1" label="Diagnose equipment failure"
      description="Identify root cause using sensor data"
      ordId="my.mes:apiResource:EquipmentOEEAnalytics:v1"/>
```

Extracted test case:
```json
{
  "process_id": "proc_machine_breakdown_v2",
  "process_title": "Machine Breakdown",
  "step_index": 1,
  "input": "Machine Breakdown process: Diagnose equipment failure — Identify root cause using sensor data",
  "label_raw": "Diagnose equipment failure — Identify root cause using sensor data",
  "expected_ordId": "my.mes:apiResource:EquipmentOEEAnalytics:v1",
  "is_gt": true
}
```

---

#### 2.1.6 Evaluation (`evaluate.py`)

All 6 methods (A–E + Method S) evaluated on Clean-ORD only. See **`docs/IMPLEMENTATION.md`** for method descriptions.

**Why Clean-ORD only?** The design-time question is whether ORD metadata — without enrichment — is sufficient to bridge the Semantic BPM gap. Enriched-ORD would pre-answer the question; the clean baseline establishes the starting point.

| Metric | Definition | Applies to |
|---|---|---|
| **P@1** | First candidate = expected_ordId | All methods |
| **R@5** | expected_ordId in top-5 candidates | All methods |
| **MRR** | Mean Reciprocal Rank | All methods |
| **Candidate Recall** | expected_ordId anywhere in candidate set | All methods |

Results: `results/design-time/` · Web: `http://localhost:4321/results/`

---

### 2.2 Run-Time Evaluation

**Question:** How much does ORD enrichment improve retrieval quality across different orchestration modes and methods?

The Run-Time evaluation tests the full orchestration pipeline: natural-language user requests must be routed to the right skill (if applicable) and resolved to the correct ORD resources. The key experimental variable is Clean-ORD vs. Enriched-ORD — Δ (the difference in performance between the two states) measures the value of the enrichment fields added in Phase 2. This directly tests the thesis claim: *process-derived ORD metadata improves agent orchestration*.

Cases are adversarially constructed (Generator → Solver → Judge) to certify that they require structured retrieval — any case that the Baseline-Solver (Method S) can answer without structure is rejected as TOO_EASY before entering the benchmark.

---

#### 2.2.1 Query Taxonomy

In practice, enterprises have large portfolios of modelled processes (BPMN/CMMN) partially or fully linked to their IT landscape. An orchestrator must handle four fundamentally different request types simultaneously:
1. Requests that map to a known, pre-modelled process → execute the skill end-to-end
2. Requests that partially match a skill but require additional capabilities not modelled → hybrid execution
3. Requests with no matching process → pure ad-hoc retrieval
4. Requests for capabilities that don't exist in the landscape → refusal

The query taxonomy maps each case to an orchestration mode and is designed to cover the full spectrum of realistic enterprise orchestration:

| Query Class | Mode | What it tests | Steps | Cases |
|---|---|---|---|---|
| **Explicit Multi-Step** | Skill-Guided | Routing to the right skill for a fully modelled process | 4–8 ordered | 30 |
| **Implicit Multi-Step** | Skill-Adjusted | Gap inference — skill covers core, extra resources needed | skill + 1–3 gaps | 20 |
| **Single-Intent** | Dynamic | Ad-hoc single-resource retrieval (P1/P2/P3 problems) | 1 resource | 20 |
| **Multi-Intent** | Dynamic | Ad-hoc multi-resource retrieval | 2–3 independent | 20 |
| **Out-of-Scope** | Out-of-Scope | Refusal — no matching resource exists | 0 | 20 |

**Total: 110 run-time cases**

Skill-Guided represents the ideal Semantic BPM scenario (process fully modelled). Skill-Adjusted represents the realistic partial-coverage case. Dynamic tests genuinely novel requests with the three core retrieval problems. Out-of-Scope tests whether the orchestrator can recognise the boundary of its knowledge.

**Note:** The 30 Skill-Guided cases use 15 BPMN + 15 CMMN process models. At run-time all 30 are classified as `explicit_multi_step` — the user prompt does not expose the underlying model type.

---

#### 2.2.2 Test Case Generation (`generate_*.py`)

All 110 run-time cases are built through the same adversarial loop. The three-party design certifies difficulty objectively: any case that the Baseline-Solver (Method S, no-retrieval) can answer is rejected as `TOO_EASY` and replaced with a harder prompt. This guarantees every accepted case requires structured retrieval.

```
┌─────────────┐      ┌──────────────────┐      ┌───────────────┐
│  GENERATOR  │─────▶│   Method S gate  │─────▶│     JUDGE     │
│  (LLM)      │      │ (no-retrieval,   │      │  (LLM)        │
│             │      │  Clean-ORD)      │      │               │
└─────────────┘      └──────────────────┘      └───────────────┘
      ↑                      │ fails                   │ accepts
      └──────harder───────────┘                         ↓
                                               provenance/{case_id}.json
```

**Generator** produces `user_prompt`, `expected_steps`, `problems_exercised`. **Method S** certifies difficulty (gate fails → TOO_EASY, max 10 iterations). **Judge**: C1 deterministic (ordIds exist), C2+ LLM (realistic prompt, no resource names, mode-specific checks).


---

**SKILL-GUIDED (30 cases, `generate_skill_guided.py`)**

*Why this design:* The user describes a business need in natural language without naming the process or skill. The challenge is routing — the orchestrator must recognise that the request maps to a registered multi-step process and commit to it rather than doing ad-hoc retrieval. Ground truth = the 4 GT-eligible steps of the matched process model.

```
INPUT:   1 process model (BPMN/CMMN) + SKILL.md + enrichment from 2.1
GENERATOR: user_prompt from process scenario — no skill/resource names
VALIDATOR: V1 ordIds exist · V2 GT-eligible · V3 no literal refs in prompt
JUDGE:   C1 realistic · C2 coherent with process · C3 skill covers end-to-end
```

<details>
<summary>Log example — sg-01 · benchmark/test_cases/runtime/logs/provenance/sg-01.json</summary>

```json
{
  "case_id": "sg-01", "mode": "skill_guided", "skill_id": "proc_022",
  "accepted_case": {
    "user_prompt": "We need to streamline our product transition process and ensure everything stays compliant..."
  },
  "evolution_log": [{
    "iteration": 1, "outcome": "ACCEPTED",
    "solver_output": { "predicted": "sap.s4:agent:BOMComplianceAutomationAgent:v1", "correct": false },
    "judge_results": { "C1": true, "C2": true, "C3": true, "C4": true, "C5": true },
    "judge_response": "Prompt is realistic, no skill/resource names, matches product transition scenario end-to-end."
  }]
}
```
Method S predicted the wrong resource (BOM Compliance Agent instead of the process skill) → difficulty certified → ACCEPTED.
</details>

---

**SKILL-ADJUSTED (20 cases, `generate_skill_adjusted.py`)**

*Why this design:* Most real enterprise requests don't map perfectly to one process — they extend it with needs not captured in the model. The user prompt describes the full scenario implicitly, including the gap. The orchestrator must use the skill for the core flow and separately retrieve the gap resources without being told what they are.

```
INPUT:   1 skill + 1–3 gap resources (not in skill, sim ≥ 0.25 to skill, GT-eligible)
GENERATOR: user_prompt extends scenario with implicit gap dependencies
VALIDATOR: V1 gaps exist · V2 not in skill · V3 sim ≥ 0.25 · V4 no literal refs
JUDGE:   C1 skill covers core (not gaps) · C2 gaps implied not stated · C3 coherent
```

<details>
<summary>Log example — sa-01 · benchmark/test_cases/runtime/logs/provenance/sa-01.json</summary>

```json
{
  "case_id": "sa-01", "mode": "skill_adjusted", "skill_id": "proc_033",
  "gap_resources": ["sap.ariba:apiResource:MaterialAndVendorMasterDataAPI:v1"],
  "accepted_case": {
    "user_prompt": "We need to establish a comprehensive procurement and delivery workflow..."
  },
  "evolution_log": [
    { "iteration": 1, "outcome": "TOO_EASY", "solver_output": { "predicted": "sap.crm:apiResource:CustomerAccountDisputeManagement:v1" } },
    { "iteration": 2, "outcome": "ACCEPTED",
      "judge_results": { "C1": true, "C2": true, "C3": true } }
  ]
}
```
First attempt TOO_EASY (solver guessed something plausible) → prompt mutated to be more implicit → second attempt ACCEPTED.
</details>

---

**DYNAMIC (40 cases, `generate_dynamic.py`)**

*Why this design:* Ad-hoc requests have no pre-modelled skill. The three sub-types target the three core failure modes the thesis identifies:
- **Agent Sprawl**: user doesn't know which system handles the capability; correct resource has a HIGH-tier neighbor from a different namespace
- **Semantic Sensitivity**: user describes the need without using vocabulary from the resource descriptor
- **Multi-resource**: user needs 2–3 independent capabilities in one request

```
INPUT:   GT resource(s) with HIGH neighbors · problem type determines selection
VALIDATOR: V1 GT-eligible · V2 HIGH neighbor exists · V3 no covering skill · V4 vocab check
JUDGE:   C1 realistic · C2 P-label verifiable · C3 distractor plausible but wrong
```

<details>
<summary>Log example — dy-01 (P1) · benchmark/test_cases/runtime/logs/provenance/dy-01.json</summary>

```json
{
  "case_id": "dy-01", "mode": "dynamic", "query_class": "single_intent", "problem_type": "P1",
  "selected_resources": ["corp.itsm:apiResource:ServiceTicketOrderManagementAPI:v1"],
  "distractor": "my.mes:apiResource:ServiceTicketChangeRequestManagement:v1",
  "accepted_case": {
    "user_prompt": "I need to pull up a recent issue that one of our customers reported last week..."
  },
  "evolution_log": [{
    "iteration": 1, "outcome": "ACCEPTED",
    "solver_output": { "predicted": "", "correct": null },
    "judge_results": { "C1": true, "C2": true, "C3": true }
  }]
}
```
P1: same service-ticket concept in two different systems (ITSM vs. MES). Solver skipped for P1 (structurally hard by construction). Judge verified P-label is visible from prompt.
</details>

---

**OUT-OF-SCOPE (20 cases, `generate_out_of_scope.py`)**

*Why this design:* A production orchestrator must refuse gracefully when asked for something outside its landscape — picking a tangentially related resource is worse than refusing. These cases include adjacent capabilities (ESG scoring, demand forecasting) and clearly foreign ones (weather, social media). Programmatic absence check as V1 validator ensures the capability is genuinely absent.

```
VALIDATOR: V1 text_sim < 0.7 to all GT-capable resources (absence certified)
JUDGE:   C1 realistic request · C2 genuinely absent · C3 adjacent resource identifiable
```

<details>
<summary>Log example — oos-01 · benchmark/test_cases/runtime/logs/provenance/oos-01.json</summary>

```json
{
  "case_id": "oos-01", "mode": "out_of_scope",
  "topic": "Supplier risk scoring using external market data",
  "accepted_case": {
    "user_prompt": "We need a way to automatically flag suppliers whose credit ratings or financial health indicators fall below our risk threshold..."
  },
  "evolution_log": [{
    "iteration": 1, "outcome": "ACCEPTED",
    "judge_results": { "C1": true, "C2": true, "C3": false },
    "judge_response": "Realistic enterprise request. External credit/financial data is genuinely absent from the landscape."
  }]
}
```
No Solver gate — OOS has no GT to fail on. Validator confirmed text_sim < 0.7 for all resources. Note C3=false (adjacent capability not identifiable) — still accepted because C1+C2 passed.
</details>

---

#### 2.2.3 Evaluation (`evaluate.py`)

Each orchestration mode tests one specific capability. The evaluation is mode-centric: one primary metric per mode directly answers whether that capability worked. All other metrics are collected for diagnostic analysis.

| Mode | Primary metric | What it measures | All metrics collected |
|---|---|---|---|
| **Skill-Guided** | **Routing-Acc** | Did the orchestrator recognise this as a skill request and route to the right skill? Once the skill matches, resources follow deterministically from `ord_confirmed` — no retrieval needed. | Routing-Acc · Tokens/case |
| **Skill-Adjusted** | **Gap-Detection** | Did the orchestrator find the gap resources not covered by the matched skill? The correct skill is provided via `hint_skill_id` — routing is deliberately bypassed so the benchmark isolates gap inference in isolation. Routing-Acc would be trivially 1.0 and is not collected. | Gap-Detection · Routing-Acc · Tokens/case |
| **Dynamic** | **Top-1** | Did the method find the right resource for an ad-hoc request with no matching skill? | Top-1 · Top-5 · Routing-Acc · Tokens/case |
| **Out-of-Scope** | **Refusal-Rate** | Did the method correctly return nothing rather than hallucinating a match? | Refusal-Rate · False-Pick-Rate · Tokens/case |

**Evaluation matrix (primary metric per mode, Δ = Enriched − Clean):**
```
              Clean-ORD    Enriched-ORD    Δ        Primary metric
Skill-Guided: routing_c    routing_e       Δ_sg  ←  Routing-Acc
Skill-Adj:    gap_c        gap_e           Δ_sa  ←  Gap-Detection
Dynamic:      top1_c       top1_e          Δ_dy  ←  Top-1
OOS:          refusal_c    refusal_e       Δ_oos ←  Refusal-Rate
```
Each row run for 6 methods (A–E + S) × 2 ORD states. Δ > 0 means enrichment helps.

Results: `results/runtime/` · Web: `/results/` · Per-mode logs: `results/runtime/<mode>/records.jsonl` · Per-case traces: `results/runtime/<mode>/traces/<condition>/<case_id>.json`

---








<br>


# APPENDIX

## A.1 Full Logging Specification

**Everything is logged.** Every generation attempt, validation result, judge verdict, and accepted output is written to a log file.

| File | Phase | Contents |
|---|---|---|
| `process_construction_log.json` | Process model generation | Every attempt: resource_pool, process XML, V1–V6 results, J1–J6 verdicts, judge_response, outcome, tokens |
| `skill_construction_log.json` | SKILL.md generation | Every attempt: process_id, SKILL.md content, S1–S4, SQ1–SQ3, judge_response, outcome |
| `design_time/activity_cases.json` | Design-time extraction | All ~240 cases: process_id, step_index, input, expected_ordId, capability |
| `provenance/{case_id}.json` | Run-time construction | Full evolution log per case (Section 2.2.5) |
| `enrichment_log.json` | Enrichment derivation | Per-resource: process step, field values written |
| `evaluation/design_time_results.json` | Design-time evaluation | Per-case: method, predicted_ordId, P@1, rank, tokens |
| `evaluation/runtime_results.json` | Run-time evaluation | Per-case × method × ORD-state: CR@k, candidate_recall, tokens |

---

## A.2 Key Design Decisions

| Decision | Rationale |
|---|---|
| **Phase 1: Landscape** | |
| Iterative generation (not modify) | New resources with confirmed structural profiles; no oscillation, clean provenance |
| Pre-check sim before LLM call | Eliminates wrong-tier failures without LLM cost |
| HIGH before MEDIUM per round | Maximises shared coverage across resources |
| Per-system cap (30 max) | Balanced landscape; prevents dominant system absorption |
| sap.odm for all 10 systems | Shared vocabulary enables cross-system similarity signal |
| 50 entity types (40 + 10 cross-domain) | Bridge types create MEDIUM connections between isolated domains |
| Tier targets 3/5/5 | Calibrated: achievable without forcing duplicates; minimum for all problem types |
| Remove `industry` from metric | Always empty → wasted computation; drop rather than keep as dead dimension |
| **Phase 2: Experimental Design** | |
| Clean-ORD vs. Enriched-ORD as experimental variable | The thesis claim is that enrichment improves retrieval; this design makes that claim testable and falsifiable |
| Enrichment from process models (Design-Time Flow) | Capabilities/useCases/processNext derived from process steps (BPMN/CMMN) — grounded in actual process semantics, not invented |
| Capabilities and useCases added to ambiguity metric for Enriched state | Metric must reflect available information; Clean and Enriched states should have different scores to measure the intervention |
| Two Solver variants (clean + enriched) | Consistency: Method S (Baseline-Solver) certifies difficulty, Solver@273-enriched measures baseline enrichment benefit |
| ToolLinkOS query taxonomy | 6 query classes cover the full complexity spectrum; comparison with related work is direct |
| Multi-step for SG/SA, single/multi for Dynamic | Mirrors real orchestration: processes are ordered, ad-hoc requests are not |
| New process models from 273 landscape | Old SKILL.md files reference old ordIds; new processes guarantee alignment |
| Adversarial construction | Prevents benchmark overfitting; difficulty certified objectively; audit trail automated |
| 30 cases per mode | Sufficient for McNemar significance; 120 total comparable to ToolLinkOS (503) scale for a specialised domain benchmark |
| P1/P2/P3 tracked per Dynamic case | Fine-grained analysis of which problems each method solves; supports thesis argument about P1–P3 as distinct failure modes |
| Judge C1 deterministic first | ordId existence check is free; no LLM cost for structurally invalid cases |
| Evolution log per case | Full auditability; appendix cites provenance files directly |

---

## A.3 Implementation Decisions

Decisions made during implementation that deviated from or refined the original concept.

### Skill-Guided: Two-Phase Prompt Construction

**Original concept:** Generator → Method S (Baseline-Solver) gate → Judge. Solver must fail before a case is accepted.

**Implemented:** SG cases went through the Solver gate during the initial generation (see `generate_skill_guided.py:150`). However, the resulting prompts were long and explicit, which created routing-evaluation noise (the planner sometimes classified them as `skill_adjusted` rather than `skill_guided`). In commit `6429a4cac` ("SG case prompts rewritten") the 30 SG prompts in `benchmark/test_cases/runtime/output/skill_guided.json` were replaced with shorter, more focused variants intended to make the routing intent unambiguous. The new prompts were **not re-validated** through the Solver gate.

**Consequence:** The provenance logs in `benchmark/test_cases/runtime/logs/provenance/sg-*.json` reflect the original (gated) prompts; the actually evaluated prompts in the output JSON differ. Since the Skill-Guided evaluation reports Routing-Accuracy as the primary metric (not retrieval P@1), this is acknowledged as a documented methodological caveat. The post-hoc certification in `benchmark/certification/v2/` re-runs Method S five times on the current SG prompts to quantify what fraction would still pass a stricter gate.

### Skill-Adjusted: Solver Gate Active

The SA generator (`generate_skill_adjusted.py:164`) applies the Solver gate against the gap resources (`solver_check(user_prompt, resources, gap_ids)`). All 20 SA prompts in the output file match their provenance `accepted_case.user_prompt` exactly.

### Dynamic: Solver Gate Active for All Cases

The DY generator (`generate_dynamic.py:252`) applies the Solver gate to all 40 Dynamic cases (Single-Intent and Multi-Intent alike), against `gt_ids[:1]`. This contradicts an earlier draft of this document that claimed Single-Intent P1/P2/P3 cases skipped the gate; the code does not skip them. All 40 DY prompts in the output file match their provenance `accepted_case.user_prompt` exactly.

### Dynamic: Single-Intent V3 Fix

**Problem:** V3 originally blocked cases where any skill covers all GT ordIds. For Single-Intent cases (1 resource), almost every GT resource appears in at least one skill. This made all Single-Intent cases fail V3.

**Fix:** V3 only applies when `len(gt_ids) > 1`. A single resource can legitimately appear in a skill without that making the query a "Skill-Guided" case — the Dynamic mode tests ad-hoc retrieval to a specific resource, not skill routing.

### Dynamic: Actual P-Problem Distribution

**Target:** 10 P1 + 10 P2 + 10 P3 single-intent cases.

**Actual result:** 19 P1 · 1 P2 · 0 P3 (all 20 single-intent cases).

**Reason:** `select_p2_pair` requires a HIGH neighbor with *identical* entity types across namespaces — this is rare in the landscape because most HIGH pairs differ in at least one ET. `select_p3_resource` requires text_sim(prompt, GT_desc) < 0.3 to be enforced, which the judge rarely confirmed. In practice, the generator defaulted to P1 (cross-namespace HIGH pairs) for almost all single-intent cases because these are structurally abundant.

**Scientific implication:** The 20 single-intent cases are predominantly P1 (Agent Sprawl) rather than a balanced P1/P2/P3 split. This means the Dynamic evaluation primarily tests cross-namespace disambiguation, not vocabulary drift or context sensitivity for single resources. The P-label is tracked per case for analysis, so the actual distribution is transparent in the provenance logs.

### Out-of-Scope: No hard/easy split

**Original concept:** 20 hard (adjacent capabilities) + 10 easy (foreign capabilities). Total 30.

**Implemented:** 20 cases from a unified topic pool, no hard/easy classification. Reasoning:
- The taxonomy table specifies 20 OOS cases.
- The hard/easy distinction adds complexity without corresponding evaluation value — OOS evaluation only measures refusal rate, not difficulty.
- Judge prompt grounded in landscape ("does our specific 10-system landscape cover this?") rather than generic enterprise software coverage.

### SG: Multi-Pass Skill Reuse

**Problem:** 5 of 30 skills had no GT resources accessible in the landscape (`len(gt_resources) < 2`), leaving 25/30 cases.

**Fix:** Skills pool extended to 3 passes; each skill reused at most 2 times with different prompts. This reached 30/30.

### Query Taxonomy Mapping

Final implementation vs. concept:

| Query Class | Cases | Mode | Notes |
|---|---|---|---|
| Single-Intent | 20 | Dynamic | P1/P2/P3 labels tracked per case |
| Multi-Intent | 20 | Dynamic | 2 resources, different namespaces |
| Explicit Multi-Step | 30 | Skill-Guided (BPMN + CMMN) | All 30 classified as explicit_multi_step; underlying process may be BPMN or CMMN |
| Implicit Multi-Step | 20 | Skill-Adjusted | 1 skill + 1-2 gap resources |
| Implicit Multi-Step | 20 | Skill-Adjusted | 1 skill + 1-2 gap resources |
| Out-of-Scope | 20 | Out-of-Scope | No refusal check; judge validates absence |

---

## A.4 Methodological Limitations & Design Decisions

These points address known limitations and anticipated reviewer questions. Acknowledging them proactively is more credible than leaving them for a committee to discover.

---

### Self-Preference Bias in LLM-as-Judge

**Risk:** Generator and Judge are both Claude Haiku instances (the same model family). A model may rate its own outputs favourably — not because they are objectively good, but because they match its own latent distribution. This is the "self-preference bias" documented in LLM evaluation literature (e.g. Zheng et al. 2023).

**Mitigating factors in this benchmark:**
1. The Validator (V1–V6, S1–S4) runs before the Judge and filters structural failures deterministically — the Judge never sees invalid outputs.
2. The Judge criteria are narrow and verifiable: "Does this ordId exist?" (C1), "Is no resource name in the prompt?" (C3) — these are not stylistic preferences but factual checks.
3. The Baseline-Solver (Method S) (Method S) provides an independent difficulty certification that is model-agnostic: it simply checks whether the flat-list prediction matches the expected ordId.

**Acknowledged limitation:** For subjective criteria (J5 "coherent enterprise story", C2 "sounds like real enterprise request"), self-preference bias cannot be ruled out. A cross-model setup (e.g. GPT-4o as Judge for Claude-generated outputs) would be methodologically stronger. This is noted as future validation work.

---

### Baseline-Solver (Method S): Design-Time vs. Run-Time Role

**Run-Time:** The Solver gate certifies difficulty for SA, DY, and SG cases. A case is accepted if Method S fails on one call — a single failure is treated as sufficient certification that the prompt requires structured retrieval. The gate checks: SA → `gap_ids`, DY → `gt_ids[:1]`, SG → `gt_ids[:1]`. Up to 15 iterations are attempted before a case is abandoned. Out-of-Scope (20) has no GT and therefore no gate; absence is certified programmatically via `text_sim < 0.7` against all GT-eligible resources.

**Design-Time:** No Solver gate is used. This is intentional:
- Cases are deterministically extracted from process models that were adversarially constructed. The `expected_ordId` is not retrieved — it is an explicit assignment (`ordId` attribute in the process XML).
- A Solver gate on Design-Time cases would eliminate cases where the activity description clearly matches the resource — but that is desirable. Design-Time measures the full difficulty spectrum from easy (non-GT steps) to hard (GT steps with HIGH-tier distractors). The GT/non-GT split replaces the adversarial gate.
- The ambiguity report (H≥3, M≥5, L≥5 targets) is the structural difficulty guarantee for GT-eligible resources.

---

### Equal Weighting in the Ambiguity Metric

**Design choice:** All six similarity dimensions (text, entityTypes, lineOfBusiness, tags, industry, localId) are weighted equally because no empirical basis exists for differential weighting at benchmark construction time.

**Anticipated reviewer question:** What if entity types deserve higher weight than tags?

**Response:** The metric is used exclusively for *landscape construction* — to ensure that every GT-eligible resource has enough structurally similar neighbors to create retrieval challenges. The absolute values of the similarity scores do not appear in the evaluation metrics (P@1, MRR, CompleteRecall@k). A sensitivity analysis varying the dimension weights would be meaningful if the metric were used as a primary result; since it is a construction tool, equal weighting is the least-biased default. A brief sensitivity analysis is planned for the thesis appendix.

---

### Out-of-Scope Hallucination Risk

**Risk:** Methods A–E might "pick" a resource for an OOS query not because the resource is actually relevant, but because the model hallucinates a connection. This false-pick rate is independent of whether the ORD state is Clean or Enriched — it is a model-level artifact, not a benchmark-quality signal.

**Mitigation in evaluation:**
- The OOS evaluation tracks *False-Pick Rate* and *Refusal Rate* separately.
- Δ (Clean vs. Enriched) for OOS cases is expected to be near zero — enrichment fields should not affect refusal behaviour for genuinely absent capabilities.
- If Δ_OOS is non-zero and positive (enrichment increases false picks), this indicates that useCases/capabilities descriptions inadvertently resemble OOS request vocabulary. This would be a finding worth reporting, not an artifact to suppress.
- Methods that cannot refuse (Method A by construction) will always have False-Pick Rate = 1.0 on OOS cases regardless of ORD state — this is noted in the evaluation setup.

--- Included here as a documented design decision: Method F is only meaningful after the A–E comparison has established which methods are strong on which problem types.

**Concept:** A meta-agent that offers Methods A–E as callable tools and selects the appropriate retrieval strategy per request based on its characterisation of the query.

```
Method F (Meta-Agent):
  Input: user_prompt
  Step 1: classify query (query_class from ToolLinkOS taxonomy, problem type P1/P2/P3)
  Step 2: route to best-fit method:
    - Single-Intent, no cross-namespace → Method A (fast, cheap)
    - Cross-namespace ambiguity (P1) → Method C (graph walk, cross-namespace bonus)
    - Implicit Multi-Step → Method D (typed tools, skill registry)
    - Low-confidence on all → ensemble vote (A+C+D)
  Step 3: return result + explanation
```

**Why after the comparison:** The routing rules in Step 2 require empirical evidence from the A–E comparison. Without knowing which method wins on P1/P2/P3, the routing is guesswork. The benchmark provides exactly this evidence.

**If results support it:** Method F could be evaluated as a post-hoc addition using the same 110 test cases without additional case construction.

---

## A.5 File Structure

```
benchmark/
  landscape/
    generation/
      generate_seeds.py       — 30 seed resources (3 per system)
      generate_iterative.py   — round-based iterative generation
      reduce_near_dups.py     — rewrite/remove pairs with full_sim ≥ 0.75
      enrich_landscape.py     — tier thresholds + shared utilities
      validate_ord.py         — spec validation (deterministic, no LLM)
      validate_taxonomy.py    — sap.odm structural checks
      ord_spec_rules.json     — required fields per resource type
    logs/
      enrichment_log.json     — all actions: seed / iterative / dedup phases
      near_dup_pairs.json     — resolved near-duplicate pairs
    systems/
      sap.odm/ord.json        — 50 entity types (shared vocabulary)
      sap.s4/ord.json         — Clean-ORD (~27 resources per system)
      sap.s4/ord_enriched.json — Enriched-ORD (capabilities, useCases, processNext, partOfGroups)
      ...                     — one ord.json + ord_enriched.json per namespace

  ambiguity/
    run_ambiguity.py
    landscape_ambiguity_report.json          — Clean-ORD scores
    landscape_ambiguity_report_enriched.json — Enriched-ORD scores (optional, Phase 2)
    README.md

  test_cases/
    design_time/
      generate_processes.py
      generate_skills.py
      enrich_from_processes.py
      extract_cases.py
      evaluate.py
      logs/
        process_construction_log.json
        skill_construction_log.json
        enrichment_log.json
      output/
        activity_cases.json
        processes/
        skills/

    runtime/
      generation/
        generate_skill_guided.py
        generate_skill_adjusted.py
        generate_dynamic.py
        generate_out_of_scope.py
        # solver_baseline.py → see src/methods/method_s.py
      evaluate.py
      logs/
        provenance/
      output/
        skill_guided.json
        skill_adjusted.json
        dynamic.json
        out_of_scope.json
```
