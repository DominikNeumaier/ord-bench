"""Generate Out-of-Scope run-time cases (20).

Capabilities not covered by the benchmark landscape (ERP, HR, Procurement,
CRM, Manufacturing, Safety/EHS, ITSM, PLM, Marketing).

No Solver check — OOS has no GT to fail on.
Validator: programmatic absence check (text similarity to any resource).
Judge: landscape-aware — checks against our 10 specific systems.

Output: data/test_cases/runtime/output/out_of_scope.json
        data/test_cases/runtime/logs/provenance/oos-*.json
"""
from __future__ import annotations

import json
import re
import sys
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from src.test_cases.runtime.generation._common import (
    load_resources, save_provenance, save_output, now_iso, MAX_ITERATIONS,
    OUTPUT_DIR,
)
from src import llm

TARGET = 20
RANDOM_SEED = 44
ABSENCE_SIM_THRESHOLD = 0.85

TOPICS = [
    "ESG / sustainability scoring and carbon footprint tracking",
    "Demand forecasting and inventory replenishment prediction",
    "Automated contract generation and clause negotiation",
    "Push notification orchestration and mobile engagement",
    "Employee sentiment analysis and engagement scoring",
    "Supplier risk scoring using external market data",
    "Regulatory change monitoring and auto-compliance alerting",
    "Real-time production cost simulation",
    "Predictive maintenance scheduling based on failure probability",
    "Workforce skill gap analysis and training recommendation",
    "Customer churn prediction and retention intervention",
    "Dynamic pricing optimization for sales orders",
    "Cross-system master data governance and deduplication",
    "Automated approval routing based on spend thresholds",
    "Sustainability reporting (GRI/CSRD) data aggregation",
    "Intraday cash flow forecasting",
    "AI-driven job description generation",
    "Real-time currency hedging and FX risk management",
    "Knowledge management and internal wiki search",
    "Automated lease accounting under IFRS 16",
    "Weather forecasting and climate data retrieval",
    "Social media post scheduling and engagement tracking",
    "Hotel and meeting room booking",
    "Ridesharing and employee transport coordination",
    "Consumer payment processing and checkout",
    "Flight booking and travel itinerary management",
    "Restaurant reservation management",
    "Personal financial budgeting and expense tracking",
    "Online gaming and esports platform management",
    "Sports match scheduling and ticketing",
]


def _text_sim(a: str, b: str) -> float:
    def tok(t): return set(re.findall(r'\w+', t.lower()))
    ta, tb = tok(a), tok(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def validate(prompt: str, resources: list[dict]) -> tuple[bool, str]:
    for r in resources:
        sim = _text_sim(prompt, f"{r['title']} {r.get('shortDescription', '')}")
        if sim > ABSENCE_SIM_THRESHOLD:
            return False, f"C1: '{r['ordId'].split(':')[2]}' sim={sim:.2f}"
    return True, ""


def judge(prompt: str) -> tuple[bool, dict, str, int]:
    sys_p = "You are a quality judge for a synthetic enterprise benchmark. Answer ONLY with valid JSON."
    user_p = f"""Does this request fall OUTSIDE our benchmark landscape?

Our landscape covers: ERP, HR, Procurement, CRM, Manufacturing, Safety/EHS, ITSM, PLM, Marketing/CX.
It does NOT cover: forecasting/prediction, sustainability/ESG scoring, translation, social media,
booking/reservations, payment processing, sentiment analysis, knowledge management, external data feeds,
gaming, weather, or personal finance.

user_prompt: {prompt}

Return JSON:
{{
  "C1": true/false,  // sounds like a realistic enterprise or business request
  "C2": true/false,  // this capability is NOT in our landscape systems
  "accepted": true/false,
  "reason": "one sentence if rejected"
}}"""
    text, meta = llm.chat(user_p, system=sys_p)
    try:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        data = json.loads(m.group()) if m else {}
        results = {"C1": data.get("C1"), "C2": data.get("C2"), "C3": True}
        return bool(data.get("accepted", False)), results, text, meta["tokens"]
    except Exception:
        return False, {"C1": None, "C2": None, "C3": None}, text, meta["tokens"]


def build_prompt(topic: str, variant: int) -> str:
    mutation = "\nPhrase it more specifically with enterprise context." if variant >= 1 else ""
    return f"""Write a realistic request for a capability outside standard ERP/HR/CRM/manufacturing systems.

Topic: {topic}
Rules: Sound like a real business user. 1-2 sentences. No system names.{mutation}

Output ONLY the request text."""


def run():
    resources = load_resources("clean")
    rng = random.Random(RANDOM_SEED)

    existing_path = OUTPUT_DIR / "out_of_scope.json"
    accepted_cases = json.loads(existing_path.read_text()) if existing_path.exists() else []
    existing_topics = {c.get("topic", "") for c in accepted_cases}
    print(f"Continuing from {len(accepted_cases)} existing cases")

    topics = [t for t in TOPICS if t not in existing_topics]
    rng.shuffle(topics)

    for topic in topics:
        if len(accepted_cases) >= TARGET:
            break

        print(f"  {topic[:55]}...")
        evolution_log = []

        for attempt in range(1, MAX_ITERATIONS + 1):
            user_prompt, gen_meta = llm.chat(build_prompt(topic, attempt - 1))
            user_prompt = user_prompt.strip().strip('"')

            v_ok, v_fail = validate(user_prompt, resources)
            if not v_ok:
                evolution_log.append({"iteration": attempt, "outcome": "VALIDATOR_FAIL", "validator_failure": v_fail})
                continue

            j_ok, j_results, j_response, j_tokens = judge(user_prompt)
            entry = {"iteration": attempt, "generator_output": {"user_prompt": user_prompt},
                     "generator_tokens": gen_meta["tokens"], "judge_results": j_results,
                     "judge_response": j_response[:300], "judge_tokens": j_tokens,
                     "outcome": "ACCEPTED" if j_ok else "JUDGE_FAIL"}
            evolution_log.append(entry)

            if not j_ok:
                print(f"    attempt {attempt}: JUDGE FAIL")
                continue

            case_id = f"oos-{len(accepted_cases)+1:02d}"
            case = {"case_id": case_id, "mode": "out_of_scope", "query_class": "out_of_scope",
                    "topic": topic, "user_prompt": user_prompt, "expected_ordIds": []}
            save_provenance(case_id, {"case_id": case_id, "mode": "out_of_scope", "topic": topic,
                                      "timestamp": now_iso(), "evolution_log": evolution_log, "accepted_case": case})
            accepted_cases.append(case)
            print(f"    attempt {attempt}: ACCEPTED → {case_id} ({len(accepted_cases)}/{TARGET})")
            break
        else:
            print(f"    GAVE UP")

    save_output("out_of_scope.json", accepted_cases[:TARGET])
    print(f"\nDone. {min(len(accepted_cases), TARGET)}/{TARGET} OOS cases.")


if __name__ == "__main__":
    run()
