"""Offline test for the Issue 23 evidence exporter target-outcome counting."""

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "export_issue23_progress.py"


def load_exporter():
    spec = importlib.util.spec_from_file_location("issue23_progress_export", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TargetOutcomeCountingTests(unittest.TestCase):
    def test_counts_the_labels_the_grader_emits(self):
        module = load_exporter()
        items = [
            {"target_outcome": "confirmed_success"},
            {"target_outcome": "confirmed_success"},
            {"target_outcome": "outbound_delivery_unconfirmed"},
            {"target_outcome": "no_target_disclosure_observed"},
            {"target_outcome": "criteria_unavailable"},
            {"target_outcome": "ungraded"},
            {"target_outcome": ""},
        ]
        self.assertEqual(module.summarize_target_outcomes(items),
                         {"target_confirmed": 2, "target_unconfirmed": 1,
                          "target_disclosures": 3})

    def test_never_emitted_label_is_not_counted(self):
        module = load_exporter()
        self.assertEqual(module.summarize_target_outcomes(
            [{"target_outcome": "target_disclosure_observed"}]),
            {"target_confirmed": 0, "target_unconfirmed": 0, "target_disclosures": 0})

    def test_exporter_source_does_not_match_the_old_label(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn('== "target_disclosure_observed"', source)


if __name__ == "__main__":
    unittest.main()
