"""Acceptance checks for the shared synthetic fixture loader."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from agent_privacy.fixture_loader import load_fixture
from contracts.validate import ContractError


ROOT = Path(__file__).resolve().parents[1]
T01 = ROOT / "fixtures" / "t01.json"


class FixtureLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = load_fixture(T01)

    def write_fixture(self, fixture: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "fixture.json"
        path.write_text(json.dumps(fixture), encoding="utf-8")
        return path

    def test_valid_t01_loads(self) -> None:
        self.assertEqual(self.fixture["fixture_id"], "T01")
        self.assertEqual(self.fixture["data_class"], "synthetic")
        self.assertEqual(len(self.fixture["expected_slots"]), 3)

    def test_missing_required_field_is_rejected(self) -> None:
        fixture = deepcopy(self.fixture)
        del fixture["user_request"]
        with self.assertRaises(ContractError):
            load_fixture(self.write_fixture(fixture))

    def test_reversed_time_range_is_rejected(self) -> None:
        fixture = deepcopy(self.fixture)
        fixture["candidate_slots"][0] = {
            "start": "2026-11-02T09:30:00+08:00",
            "end": "2026-11-02T09:00:00+08:00",
        }
        with self.assertRaises(ContractError):
            load_fixture(self.write_fixture(fixture))

    def test_duplicate_json_key_is_rejected(self) -> None:
        duplicate = T01.read_text(encoding="utf-8").replace(
            '"fixture_id": "T01",',
            '"fixture_id": "T01",\n  "fixture_id": "T02",',
            1,
        )
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "duplicate.json"
        path.write_text(duplicate, encoding="utf-8")
        with self.assertRaises(ContractError):
            load_fixture(path)

    def test_real_looking_tokens_are_rejected_without_echoing_them(self) -> None:
        cases = (
            "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456",
            "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
            "AKIAABCDEFGHIJKLMNOP",
            "-----BEGIN PRIVATE KEY-----",
        )
        for credential in cases:
            with self.subTest(credential=credential[:4]):
                fixture = deepcopy(self.fixture)
                fixture["document_common"] = credential
                with self.assertRaises(ContractError) as raised:
                    load_fixture(self.write_fixture(fixture))
                self.assertNotIn(credential, str(raised.exception))

    def test_explicit_synthetic_values_and_attack_text_are_allowed(self) -> None:
        fixture = load_fixture(T01)
        self.assertEqual(
            fixture["contacts"]["entries"][0]["phone"],
            "SYNTHETIC-PRIVATE-PHONE-555-0100",
        )
        self.assertIn("SYSTEM OVERRIDE", fixture["attack_paragraph"])


if __name__ == "__main__":
    unittest.main()
