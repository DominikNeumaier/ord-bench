"""Shared helpers for all runtime case generation scripts."""
from __future__ import annotations

import json
import re
import random
from datetime import datetime, timezone
from pathlib import Path

from src import config, llm, loader as ord_loader

ROOT = config.ROOT
PROCESSES_DIR   = ROOT / "data" / "test_cases" / "design_time" / "output" / "processes"
SKILLS_DIR      = ROOT / "data" / "test_cases" / "design_time" / "output" / "skills"
AMBIGUITY_REPORT = ROOT / "data" / "ambiguity" / "landscape_ambiguity_report.json"
PROVENANCE_DIR  = ROOT / "data" / "test_cases" / "runtime" / "logs" / "provenance"
OUTPUT_DIR      = ROOT / "data" / "test_cases" / "runtime" / "output"

MAX_ITERATIONS = 10


# ── Data loading ─────────────────────────────────────────────────────────────

def load_resources(state: str = "clean") -> list[dict]:
    return ord_loader.load_landscape(state)


def load_ambiguity() -> dict[str, dict]:
    data = json.loads(AMBIGUITY_REPORT.read_text())
    return {r["ordId"]: r for r in data["resources"]}


def load_skills() -> list[dict]:
    """Return list of {skill_id, description, process_type, gt_ord_ids, steps}."""
    skills = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        text = path.read_text()
        fm = _parse_frontmatter(text)
        confirmed = re.findall(r'ord_confirmed:\s*([^\s\-\*\n<>]+)', text)
        enrich_path = PROCESSES_DIR / f"{path.stem}_enrichment.json"
        gt_ids = json.loads(enrich_path.read_text()).get("gt_ordIds", []) if enrich_path.exists() else confirmed
        skills.append({
            "skill_id": path.stem,
            "description": fm.get("description", ""),
            "process_type": fm.get("process-type", "bpmn"),
            "gt_ord_ids": gt_ids,
            "ord_confirmed": confirmed,
        })
    return skills


def _parse_frontmatter(text: str) -> dict:
    m = re.match(r'^---\s*\n([\s\S]*?)\n---', text)
    if not m: return {}
    out: dict = {}
    current = None
    for line in m.group(1).split("\n"):
        kv = re.match(r'^([a-zA-Z][\w-]*):\s*(.*)', line)
        if kv:
            out[kv.group(1)] = kv.group(2).strip().lstrip(">").strip()
            current = kv.group(1)
        elif current and line.startswith("  "):
            out[current] = (out[current] + " " + line.strip()).strip()
    return out


def get_resource_by_id(resources: list[dict], ord_id: str) -> dict | None:
    for r in resources:
        if r["ordId"] == ord_id:
            return r
    return None


# ── Solver@273-clean ─────────────────────────────────────────────────────────

def solver_check(prompt: str, resources: list[dict], expected_ids: list[str]) -> tuple[bool, str]:
    """Run Solver@273-clean. Returns (solver_correct, predicted_ordId)."""
    from src.methods import method_s
    result = method_s.retrieve(prompt, resources, top_k=1)
    predicted = result["candidates"][0]["ordId"] if result["candidates"] else None
    correct = predicted in expected_ids if predicted else False
    return correct, predicted or ""


# ── Provenance logging ───────────────────────────────────────────────────────

def save_provenance(case_id: str, data: dict) -> None:
    PROVENANCE_DIR.mkdir(parents=True, exist_ok=True)
    (PROVENANCE_DIR / f"{case_id}.json").write_text(json.dumps(data, indent=2))


def save_output(filename: str, cases: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / filename).write_text(json.dumps(cases, indent=2))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
