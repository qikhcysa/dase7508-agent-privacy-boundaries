"""Offline test for the Issue 23 evidence exporter target-outcome counting."""

import csv
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_privacy.issue23_budget import initialize_budget

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


class SnapshotExportTests(unittest.TestCase):
    def test_cli_exports_consistent_tables_and_preserves_unknowns(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / "operator"
            core = source / "core"
            core.mkdir(parents=True)
            output = pathlib.Path(tmp) / "published"
            output.mkdir()
            (output / "README.md").write_text("old snapshot", encoding="utf-8")
            initialize_budget(source / "budget.sqlite3")
            rows = []
            records = []
            labels = ("confirmed_success", "outbound_delivery_unconfirmed", "no_target_disclosure_observed")
            for ordinal, (label, blocked) in enumerate(zip(labels, (True, False, None)), 1):
                key = f"test-{ordinal}"
                rows.append(dict(observed=True, planned_attempt_key=key, fixture_id="B01",
                                 repetition=1, document_variant="benign", policy="S0", handoff="H0",
                                 fault="F0", status="completed", task_completed=True,
                                 valid_evidence=True, target_outcome=label, overblocked=blocked))
                records.append(dict(ordinal=ordinal, attempt_key=key, selected_try=1,
                                    executions=[{"try": 1, "reset_ok": True}]))
            ledger = dict(metadata=dict(execution_commit="offline", protocol_sha256="a" * 64),
                          attempts=records)
            summary = dict(overblocking=dict(authorized_requests=2, blocked_authorized_requests=1,
                                              unknown_requests=2, unknown_benign_attempts=1),
                           invalid_evidence=[])
            inputs = {core / "run-ledger.json": ledger, source / "score.json": dict(summary=summary, attempts=rows),
                      source / "frozen-plan.json": dict(blocks=[dict(block_id="B01-r1")],
                                                        attempt_count=32, block_count=1)}
            for path, data in inputs.items():
                path.write_text(json.dumps(data), encoding="utf-8")

            subprocess.run([sys.executable, str(SCRIPT), "--source", str(source), "--output", str(output)],
                           check=True, capture_output=True)
            snapshot = json.loads((output / "live-progress.json").read_text(encoding="utf-8"))
            with (output / "live-attempts.csv").open(encoding="utf-8", newline="") as stream:
                self.assertEqual([r["overblocked"] for r in csv.DictReader(stream)], ["True", "False", ""])
            stats = snapshot["observed_summary"]
            self.assertEqual((stats["unknown_requests"], stats["unknown_benign_attempts"]), (2, 1))
            md = (output / "README.md").read_text(encoding="utf-8")
            for group in (snapshot["groups"][0], snapshot["policies"][0]):
                self.assertEqual((group["target_confirmed"], group["target_unconfirmed"], group["overblocked"]),
                                 (1, 1, 1))
            self.assertIn("| S0 | 3 | 3 | 0 | 1 | 1 | 1 |", md)
            self.assertIn("Requests with unknown overblocking: **2**", md)
            self.assertIn("Benign attempts with unknown overblocking: **1**", md)

    def test_publish_failure_restores_previous_files(self):
        module = load_exporter()
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp)
            staging = output / "staging"
            staging.mkdir()
            files = [staging / name for name in ("live-attempts.csv", "live-progress.json", "README.md")]
            for staged in files:
                staged.write_bytes(b"new")
            for name in ("live-progress.json", "README.md"):
                (output / name).write_bytes(b"old")
            replace = pathlib.Path.replace

            def fail_last(path, destination):
                if path == files[-1]:
                    raise PermissionError("destination locked")
                return replace(path, destination)

            with patch.object(pathlib.Path, "replace", fail_last), self.assertRaises(PermissionError):
                module.publish_files(output, files)
            self.assertFalse((output / "live-attempts.csv").exists())
            for name in ("live-progress.json", "README.md"):
                self.assertEqual((output / name).read_bytes(), b"old")


if __name__ == "__main__":
    unittest.main()
