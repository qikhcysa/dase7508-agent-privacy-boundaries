"""Validate supplemental denominators and task separation without model calls."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from agent_privacy.supplements import CASES_PATH, build_cases, materialize, validate_cases
from agent_privacy.scheduler import schedule_fixture
from contracts.validate import validate


class SupplementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    def test_complete_fixed_manifest_and_attempt_count(self):
        counts = validate_cases(self.data)
        self.assertEqual(dict(counts), {"lawful_sharing": 48, "persistence_chain": 48, "h1_pressure": 96})
        self.assertEqual(sum(case.get("attempts", 1) for case in self.data["cases"]), 240)
        self.assertEqual(len({case["case_id"] for case in self.data["cases"]}), 192)

    def test_lawful_input_has_trusted_request_and_grounded_key(self):
        for case in self.data["cases"]:
            if case["family"] != "lawful_sharing":
                continue
            with self.subTest(case=case["case_id"]):
                fixture = materialize(case)["fixture"]
                validate("fixture", fixture)
                self.assertEqual(fixture["user_request"], case["trusted_user_request"])
                self.assertEqual(case["trusted_grant_template"]["recipient"], case["answer_key"]["recipient"])
                self.assertEqual(case["answer_key"]["agenda"], fixture["expected_agenda"])
                self.assertEqual(case["answer_key"]["slots"], fixture["expected_slots"])
                self.assertEqual(schedule_fixture(fixture)["slots"], fixture["expected_slots"])

    def test_chain_removes_attack_and_replaces_marker(self):
        for case in self.data["cases"]:
            if case["family"] != "persistence_chain":
                continue
            with self.subTest(case=case["case_id"]):
                inputs = materialize(case)
                first, second = inputs["task1_fixture"], inputs["task2_fixture"]
                validate("fixture", first)
                validate("fixture", second)
                self.assertIn(case["task1_marker"], json.dumps(first))
                self.assertNotIn(case["task1_marker"], json.dumps(second))
                self.assertIn(case["task2_marker"], json.dumps(second))
                self.assertNotIn(first["attack_paragraph"], json.dumps(second))
                self.assertEqual(case["task2_trusted_grants"], [])
                self.assertTrue(case["new_task_id_required"])
                self.assertEqual(schedule_fixture(first)["slots"], case["answer_key"]["task2_slots"])
                self.assertEqual(schedule_fixture(second)["slots"], case["answer_key"]["task2_slots"])

    def test_pressure_is_h1_double_failure_and_separate_grade(self):
        for case in self.data["cases"]:
            if case["family"] != "h1_pressure":
                continue
            with self.subTest(case=case["case_id"]):
                self.assertEqual(case["handoff"], "H1")
                self.assertEqual(case["fault_injection"], {"primary": "timeout", "recovery": "timeout"})
                self.assertEqual(case["grade"], "pressure_only")
                self.assertFalse(case["answer_key"]["raw_private_release_authorized"])

    def test_missing_or_edited_case_is_rejected(self):
        missing = deepcopy(self.data)
        missing["cases"].pop()
        with self.assertRaises(ValueError):
            validate_cases(missing)
        edited = deepcopy(self.data)
        edited["cases"][0]["trusted_grant_template"]["recipient"] = "mock_cloud"
        with self.assertRaises(ValueError):
            validate_cases(edited)


if __name__ == "__main__":
    unittest.main()
