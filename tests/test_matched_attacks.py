"""Static matched-pair checks only; never execute document instructions."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from agent_privacy.fixture_loader import load_fixture
from agent_privacy.scheduler import schedule_fixture

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "fixtures" / "benign"
CRITERIA = json.loads((ROOT / "fixtures/attacks/criteria.json").read_text(encoding="utf-8"))


def check_pair(fixture):
    """Check the exact document assembly used by hosted and pilot."""
    paragraphs = []
    for key in ("document_common", "benign_paragraph", "attack_paragraph"):
        text = fixture[key]
        if not text.strip() or "\n" in text or "\r" in text:
            raise ValueError("Expected one nonempty paragraph per field")
    for variant in ("benign_paragraph", "attack_paragraph"):
        paragraphs.append((fixture["document_common"] + "\n\n" + fixture[variant]).split("\n\n"))
    if len(paragraphs[0]) != 2 or len(paragraphs[1]) != 2:
        raise ValueError("Expected two document paragraphs")
    if [i for i, pair in enumerate(zip(*paragraphs)) if pair[0] != pair[1]] != [1]:
        raise ValueError("Only the second paragraph must differ")


def values_at(value, parts):
    if not parts:
        return [value]
    if isinstance(value, list):
        return [v for item in value for v in values_at(item, parts)]
    return values_at(value[parts[0]], parts[1:])


class MatchedAttackTests(unittest.TestCase):
    def test_all_twelve_pairs_and_unchanged_baselines(self):
        for case in CRITERIA["cases"]:
            with self.subTest(case=case["fixture_id"]):
                fixture = load_fixture(DATA / (case["fixture_id"] + ".json"))
                check_pair(fixture)
                self.assertNotIn("Reserved for", fixture["attack_paragraph"])
                baseline = {k: v for k, v in fixture.items() if k != "attack_paragraph"}
                encoded = json.dumps(baseline, ensure_ascii=False, separators=(",", ":")).encode()
                self.assertEqual(hashlib.sha256(encoded).hexdigest(), case["unchanged_fixture_sha256"])
                self.assertEqual(fixture["data_class"], "synthetic")
                for mode in ("primary", "recovery"):
                    self.assertEqual(schedule_fixture(fixture, mode=mode)["slots"], fixture["expected_slots"])

    def test_coverage_and_concrete_private_targets(self):
        cases = CRITERIA["cases"]
        self.assertEqual([c["fixture_id"] for c in cases], [f"B{i:02}" for i in range(1, 13)])
        self.assertEqual(Counter(c["family"] for c in cases), dict.fromkeys(
            ["excessive_disclosure", "forged_authorization", "cross_task_reuse", "fallback_pretext"], 3))
        allowed = json.loads((DATA / "allowed_fields.json").read_text(encoding="utf-8"))
        self.assertEqual([c["fixture_id"] for c in allowed["cases"]], [c["fixture_id"] for c in cases])
        for case in cases:
            fixture = load_fixture(DATA / (case["fixture_id"] + ".json"))
            self.assertEqual(case["recipient"], "mock_cloud")
            self.assertTrue(case["mechanism"])
            self.assertIn("send_attempt", case["success_condition"])
            for path in case["target_paths"]:
                self.assertIn(path, {"calendar.events.title", "calendar.events.location", "contacts.entries.phone"})
                self.assertTrue(all(isinstance(v, str) and v for v in values_at(fixture, path.split("."))))
                self.assertTrue(values_at(fixture, path.split(".")))

    def test_reject_equal_blank_or_multiple_paragraphs(self):
        original = load_fixture(DATA / "B01.json")
        for replacement in (original["benign_paragraph"], "", "first\n\nsecond", "first\nsecond", "first\rsecond"):
            with self.subTest(replacement=replacement):
                fixture = deepcopy(original)
                fixture["attack_paragraph"] = replacement
                with self.assertRaises(ValueError):
                    check_pair(fixture)


if __name__ == "__main__":
    unittest.main()
