from __future__ import annotations

import json
import re
import unittest
from unittest.mock import patch

from src import config
from src.cases import build_cases
from src.loader import load_landscape


class OrdBenchDataContractTest(unittest.TestCase):
    def test_clean_and_enriched_landscapes_share_273_ids(self) -> None:
        clean = load_landscape("clean")
        enriched = load_landscape("enriched")
        clean_ids = {r["ordId"] for r in clean}
        enriched_ids = {r["ordId"] for r in enriched}
        self.assertEqual(273, len(clean))
        self.assertEqual(273, len(clean_ids))
        self.assertEqual(clean_ids, enriched_ids)
        self.assertEqual(10, len({r["namespace"] for r in clean}))

    def test_design_time_case_counts_and_references(self) -> None:
        cases = build_cases()
        resources = {r["ordId"] for r in load_landscape("clean")}
        self.assertEqual(240, len(cases))
        self.assertEqual(120, sum(bool(c["is_gt"]) for c in cases))
        for case in cases:
            self.assertTrue(set(case["expected_ordIds"]) <= resources)

    def test_runtime_family_counts_and_references(self) -> None:
        resources = {r["ordId"] for r in load_landscape("clean")}
        expected_counts = {
            "skill_guided": 30,
            "skill_adjusted": 20,
            "dynamic": 40,
            "out_of_scope": 20,
        }
        for family, expected_count in expected_counts.items():
            path = config.RT_OUTPUT_DIR / f"{family}.json"
            rows = json.loads(path.read_text())
            self.assertEqual(expected_count, len(rows), family)
            for row in rows:
                ids = set(row.get("expected_ordIds", []))
                ids.update(row.get("expected_gap_ordIds", []))
                for step in row.get("expected_steps", []):
                    ids.update(step.get("expected_ordIds", []))
                self.assertTrue(ids <= resources, row.get("case_id"))

    def test_skill_files_match_the_published_contract(self) -> None:
        skill_dir = config.DT_OUTPUT_DIR / "skills"
        files = list(skill_dir.glob("*.md"))
        resources = {r["ordId"] for r in load_landscape("clean")}
        self.assertEqual(30, len(files))
        for path in files:
            text = path.read_text()
            steps = re.findall(r"^###\s+Step\s+\d+:\s+.+$", text, re.MULTILINE)
            confirmed = [
                value.strip()
                for value in re.findall(r"<!--\s*ord_confirmed:\s*([^>]+?)-->", text)
            ]
            self.assertEqual(8, len(steps), path.name)
            self.assertEqual(4, len(confirmed), path.name)
            self.assertTrue(set(confirmed) <= resources, path.name)

    def test_runtime_gate_uses_the_internal_frozen_solver(self) -> None:
        from src.test_cases.runtime.generation import _common

        resources = load_landscape("clean")[:2]
        expected = resources[0]["ordId"]
        fake_result = {"candidates": [{"ordId": expected, "score": 1.0}]}
        with patch(
            "src.certification.baseline_solver.retrieve", return_value=fake_result
        ) as retrieve:
            solved, predicted = _common.solver_check("test activity", resources, [expected])
        self.assertTrue(solved)
        self.assertEqual(expected, predicted)
        retrieve.assert_called_once_with("test activity", resources, top_k=1)


if __name__ == "__main__":
    unittest.main()
