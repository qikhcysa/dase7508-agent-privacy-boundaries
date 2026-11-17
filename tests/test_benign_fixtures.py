"""Validate the B01-B12 synthetic benign fixture set and answer keys."""

import json
from pathlib import Path
import unittest

from agent_privacy.fixture_loader import load_fixture
from agent_privacy.scheduler import schedule_fixture


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "fixtures" / "benign"
FIXTURE_PATHS = sorted(FIXTURE_DIR.glob("B*.json"))


class BenignFixtureTests(unittest.TestCase):
    def test_twelve_unique_synthetic_fixtures_load(self) -> None:
        self.assertEqual(len(FIXTURE_PATHS), 12)
        fixtures = [load_fixture(path) for path in FIXTURE_PATHS]
        self.assertEqual({fixture["fixture_id"] for fixture in fixtures},
                         {f"B{number:02d}" for number in range(1, 13)})
        self.assertTrue(all(fixture["data_class"] == "synthetic" for fixture in fixtures))
        self.assertTrue(all(len(fixture["expected_agenda"]) == 3 for fixture in fixtures))
        self.assertTrue(all(1 <= len(fixture["expected_slots"]) <= 3 for fixture in fixtures))

    def test_primary_and_recovery_match_each_slot_answer(self) -> None:
        for path in FIXTURE_PATHS:
            fixture = load_fixture(path)
            for mode in ("primary", "recovery"):
                with self.subTest(fixture=fixture["fixture_id"], mode=mode):
                    self.assertEqual(
                        schedule_fixture(fixture, mode=mode)["slots"],
                        fixture["expected_slots"],
                    )

    def test_agenda_answers_are_grounded_in_document_text(self) -> None:
        for path in FIXTURE_PATHS:
            fixture = load_fixture(path)
            document = fixture["document_common"].casefold()
            with self.subTest(fixture=fixture["fixture_id"]):
                self.assertTrue(
                    all(answer.casefold() in document for answer in fixture["expected_agenda"])
                )

    def test_allowed_fields_cover_each_case_and_only_public_outputs(self) -> None:
        answer_fields = json.loads((FIXTURE_DIR / "allowed_fields.json").read_text(encoding="utf-8"))
        cases = {case["fixture_id"]: case["allowed_fields"] for case in answer_fields["cases"]}
        self.assertEqual(answer_fields["schema_version"], "issue16-benign-allowed-fields-v1")
        self.assertEqual(len(answer_fields["cases"]), 12)
        self.assertEqual(set(cases), {f"B{number:02d}" for number in range(1, 13)})
        self.assertTrue(all(fields == ["agenda", "slots"] for fields in cases.values()))

    def test_b09_has_one_feasible_slot(self) -> None:
        fixture = load_fixture(FIXTURE_DIR / "B09.json")
        self.assertEqual(len(fixture["expected_slots"]), 1)
        self.assertEqual(schedule_fixture(fixture)["slots"], fixture["expected_slots"])


if __name__ == "__main__":
    unittest.main()
