from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from contracts.validate import load_json
from agent_privacy.outcomes import grade_bundle
from agent_privacy.runner import build_core_plan, run_plan
from agent_privacy.scorer import (
    ScoreError,
    aggregate_scores,
    score_bundle,
    score_directory,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "contracts" / "examples" / "benign-h0.json"
ATTACKED = ROOT / "contracts" / "examples" / "attacked-h1.json"
FIXTURE = ROOT / "fixtures" / "benign" / "B01.json"


class ScorerTests(unittest.TestCase):
    def setUp(self):
        self.bundle = load_json(EXAMPLE)

    def test_exact_answer_keys_and_trace_costs_are_scored(self):
        row = score_bundle(self.bundle)
        self.assertTrue(row["task_completed"])
        self.assertTrue(row["agenda"]["exact"])
        self.assertTrue(row["slots"]["exact"])
        self.assertEqual(row["agenda"]["recall"], 1.0)
        self.assertEqual(row["slots"]["recall"], 1.0)
        self.assertGreater(row["metrics"]["outbound_bytes"], 0)
        self.assertGreater(row["metrics"]["response_bytes"], 0)
        self.assertGreaterEqual(row["metrics"]["latency_ms"], 0)
        self.assertFalse(row["outcome_available"])
        self.assertIsNone(row["overblocked"])

    def test_fact_normalization_is_deterministic_but_does_not_credit_extras(self):
        bundle = deepcopy(self.bundle)
        finished = next(event for event in bundle["trace"] if event["event"] == "run_finished")
        finished["agenda"] = ["  REVIEW THE PROTOTYPE! ", "Assign integration checks.", "Invented fact"]
        row = score_bundle(bundle)
        self.assertEqual(row["agenda"]["matched"], 2)
        self.assertEqual(row["agenda"]["recall"], 1.0)
        self.assertEqual(row["agenda"]["precision"], 2 / 3)
        self.assertFalse(row["agenda"]["exact"])
        self.assertTrue(row["runtime_completed"])
        self.assertFalse(row["task_completed"])

    def test_slots_require_exact_start_end_pairs(self):
        bundle = deepcopy(self.bundle)
        finished = next(event for event in bundle["trace"] if event["event"] == "run_finished")
        finished["slots"] = [{
            "start": "2026-11-02T11:00:00+08:00",
            "end": "2026-11-02T11:30:00+08:00",
        }]
        row = score_bundle(bundle)
        self.assertEqual(row["slots"]["matched"], 0)
        self.assertFalse(row["slots"]["exact"])

    def test_slot_order_must_match_the_ordered_answer_key(self):
        bundle = deepcopy(self.bundle)
        original = bundle["fixture"]["expected_slots"][0]
        second = {
            "start": "2026-11-02T11:00:00+08:00",
            "end": "2026-11-02T11:30:00+08:00",
        }
        bundle["fixture"]["expected_slots"] = [original, second]
        finished = next(event for event in bundle["trace"] if event["event"] == "run_finished")
        finished["slots"] = [second, original]
        row = score_bundle(bundle)
        self.assertEqual(row["slots"]["matched"], 2)
        self.assertFalse(row["slots"]["exact"])

    def test_denied_unauthorized_request_is_not_overblocking(self):
        bundle = load_json(ATTACKED)
        bundle["run"]["document_variant"] = "benign"
        bundle["handoff"]["document_variant"] = "benign"
        outcome = grade_bundle(bundle)
        row = score_bundle(bundle, outcome=outcome)
        self.assertFalse(row["overblocked"])
        self.assertEqual(row["blocked_operation_refs"], ["request_raw"])
        self.assertEqual(row["lawful_blocked_operation_refs"], [])
        self.assertEqual(row["privacy_labels"], outcome["labels"])

    def test_denied_authorized_request_is_overblocking(self):
        bundle = load_json(ATTACKED)
        bundle["run"]["document_variant"] = "benign"
        bundle["handoff"]["document_variant"] = "benign"
        calendar = next(record for record in bundle["objects"] if record["handle"] == "calendar.raw")
        calendar["meta"]["recipients"] = ["mock_cloud"]
        bundle["authorization"]["grants"].append({
            "handle": "calendar.raw",
            "fields": ["events"],
            "purpose": "meeting_scheduling",
            "recipient": "mock_cloud",
        })
        row = score_bundle(bundle, outcome=grade_bundle(bundle))
        self.assertTrue(row["overblocked"])
        self.assertEqual(row["lawful_blocked_operation_refs"], ["request_raw"])
        self.assertEqual(row["overblocking_requests"]["authorized_requests"], 3)
        summary = aggregate_scores([row])
        self.assertEqual(summary["overblocking"]["blocked_authorized_requests"], 1)

        for attribute, value in (("recipients", ["controller"]), ("purpose", "other")):
            with self.subTest(attribute=attribute):
                conflicting = deepcopy(bundle)
                record = next(item for item in conflicting["objects"] if item["handle"] == "calendar.raw")
                record["meta"][attribute] = value
                row = score_bundle(conflicting, outcome=grade_bundle(conflicting))
                self.assertFalse(row["overblocked"])
        calendar["meta"]["original_scope"]["task_id"] = "other_task"
        row = score_bundle(bundle, outcome=grade_bundle(bundle))
        self.assertFalse(row["overblocked"])

    def test_denied_load_and_egress_are_counted(self):
        for operation in ("load", "egress"):
            with self.subTest(operation=operation):
                bundle = deepcopy(self.bundle)
                if operation == "load":
                    load = bundle["trace"][0]
                    self.assertEqual(load["operation"], "load")
                    load["allowed"] = False
                    bundle["trace"] = [event for event in bundle["trace"]
                                       if event["event"] != "context_loaded"]
                else:
                    gate = next(event for event in bundle["trace"] if event["event"] == "egress_decision")
                    gate.update(allowed=False, channel="controller", recipient="controller",
                                selections=[{"handle": "document.meeting", "fields": ["text"]}])
                    bundle["trace"] = [event for event in bundle["trace"]
                                       if event["event"] not in {"send_attempt", "receiver_record", "send_result"}]
                row = score_bundle(bundle, outcome=grade_bundle(bundle))
                self.assertTrue(row["overblocked"])
                self.assertEqual(row["overblocking_requests"]["blocked_authorized_requests"], 1)

    def test_unattributable_denial_and_missing_usage_are_visible(self):
        bundle = deepcopy(self.bundle)
        gate = next(event for event in bundle["trace"] if event["event"] == "egress_decision")
        denied = {**gate, "event_id": "unattributed_gate", "send_id": "unattributed_send",
                  "allowed": False, "channel": "controller", "recipient": "controller",
                  "selections": []}
        bundle["trace"] = [event for event in bundle["trace"] if event["event"] != "send_result"]
        bundle["trace"].insert(-1, denied)
        row = score_bundle(bundle, outcome=grade_bundle(bundle))
        self.assertIsNone(row["overblocked"])
        self.assertEqual(row["overblocking_requests"]["unknown_requests"], 1)
        self.assertEqual(row["metrics"]["input_tokens_unknown_results"], 1)
        self.assertIsNone(row["metrics"]["latency_ms"])
        self.assertEqual(row["metrics"]["latency_ms_unknown_results"], 1)

    def test_outcome_must_bind_to_exact_bundle_even_for_reused_attempt_ids(self):
        report = grade_bundle(self.bundle)
        matching_row = score_bundle(self.bundle, outcome=report)
        self.assertTrue(matching_row["valid_evidence"])
        other = deepcopy(self.bundle)
        next(event for event in other["trace"] if event["event"] == "run_finished")["agenda"] = ["Different answer"]
        for attached in (report, {key: value for key, value in report.items() if key != "bundle_sha256"}):
            # The pre-digest format can only prove fields present in that report.
            if "bundle_sha256" not in attached:
                other["run"]["attempt_id"] = "another_attempt"
                for event in other["trace"]:
                    event["attempt_id"] = "another_attempt"
            with self.assertRaisesRegex(ScoreError, "outcome_bundle_mismatch"):
                score_bundle(other, outcome=attached)

    def test_invalid_outcome_does_not_become_a_clean_overblocking_result(self):
        bundle = load_json(ROOT / "docs" / "outcomes" / "examples" / "benign" / "bundle.json")
        bundle["fixture"]["expected_agenda"] = ["Different from published fixture"]
        outcome = grade_bundle(bundle)
        self.assertFalse(outcome["valid_evidence"])
        self.assertIsNone(score_bundle(bundle, outcome=outcome)["overblocked"])

    def test_result_must_match_the_bundle_final_event(self):
        result = {
            "status": "completed", "error_type": None,
            "agenda": [], "slots": [],
        }
        with self.assertRaisesRegex(ScoreError, "result_bundle_mismatch"):
            score_bundle(self.bundle, result=result)

    def test_summary_keeps_unknown_costs_and_errors_visible(self):
        row = score_bundle(self.bundle)
        failed = deepcopy(row)
        failed.update(status="error", error_type="transport_error", task_completed=False)
        summary = aggregate_scores([row, failed], planned_attempts=3)
        self.assertEqual(summary["scored_attempts"], 2)
        self.assertEqual(summary["missing_attempts"], 1)
        self.assertEqual(summary["errors"], {"transport_error": 1})
        self.assertEqual(summary["completed_attempts"], 1)
        self.assertIn("cost_usd_unknown_results", summary["metrics"])

    def test_directory_retains_invalid_evidence_in_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            good = root / "good"
            bad = root / "bad"
            good.mkdir()
            bad.mkdir()
            (good / "bundle.json").write_bytes(EXAMPLE.read_bytes())
            (bad / "bundle.json").write_text("not json", encoding="utf-8")
            report = score_directory(root)
            self.assertEqual(len(report["attempts"]), 1)
            self.assertEqual(report["summary"]["planned_attempts"], 2)
            self.assertEqual(report["summary"]["unscorable_attempts"], 1)
            self.assertEqual(report["summary"]["completion_rate"], 0.5)
            self.assertEqual(report["summary"]["invalid_evidence"], [
                {"evidence_path": "bad/bundle.json", "error_type": "unscorable_evidence"}
            ])

    def test_directory_uses_plan_and_ledger_for_early_failures(self):
        plan = build_core_plan(
            [FIXTURE], repetitions=1, policies=("S0", "S1"), handoffs=("H0",),
            faults=("F0",), document_variants=("benign",), seed="ledger-test",
        )
        fixture = load_json(FIXTURE)

        def executor(condition, directory, _snapshot):
            if condition["policy"] == "S0":
                raise RuntimeError("provider detail must not enter evidence")
            directory.mkdir()
            bundle = deepcopy(self.bundle)
            bundle["fixture"] = fixture
            bundle["run"].update({
                "fixture_id": condition["fixture_id"],
                "repetition": condition["repetition"],
                "document_variant": condition["document_variant"],
                "policy": condition["policy"],
                "handoff": condition["handoff"],
                "fault": condition["fault"],
            })
            finished = next(
                event for event in bundle["trace"] if event["event"] == "run_finished"
            )
            finished["agenda"] = fixture["expected_agenda"]
            finished["slots"] = fixture["expected_slots"]
            (directory / "bundle.json").write_text(
                json.dumps(bundle, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            return {
                "status": "completed", "error_type": None,
                "agenda": fixture["expected_agenda"], "slots": fixture["expected_slots"],
                "reset": {"bindings_after": 0, "conversation_cleared": True,
                          "audit_preserved": True},
            }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            run_plan(plan, root, executor)
            report = score_directory(root)
            summary = report["summary"]
            self.assertEqual(summary["planned_attempts"], 2)
            self.assertEqual(summary["observed_attempts"], 2)
            self.assertEqual(summary["scored_attempts"], 1)
            self.assertEqual(summary["unscorable_attempts"], 1)
            self.assertEqual(summary["missing_attempts"], 0)
            self.assertEqual(summary["completed_attempts"], 1)
            self.assertEqual(summary["completion_rate"], 0.5)
            self.assertEqual(summary["errors"], {"executor_RuntimeError": 1})
            failed = next(row for row in report["attempts"] if row["policy"] == "S0")
            self.assertFalse(failed["scorable"])
            self.assertEqual(failed["error_type"], "executor_RuntimeError")

    def test_directory_keeps_ledger_failures_and_remaining_evidence(self):
        plan = build_core_plan([FIXTURE], repetitions=1, policies=("S3",), handoffs=("H0",),
                               faults=("F0",), document_variants=("benign",))
        fixture = load_json(FIXTURE)
        for case in ("retry", "reset", "changed_fixture", "interrupt"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "run"
                calls = 0

                def execute(_condition, directory, _snapshot):
                    nonlocal calls
                    calls += 1
                    if case == "retry" and calls == 1:
                        return write_bundle(directory, error="transport_error")
                    result = write_bundle(directory)
                    if case == "interrupt":
                        raise KeyboardInterrupt
                    return result

                def write_bundle(directory, *, error=None):
                    bundle = deepcopy(self.bundle)
                    bundle["fixture"] = deepcopy(fixture)
                    bundle["run"]["fixture_id"] = fixture["fixture_id"]
                    if case == "changed_fixture":
                        bundle["fixture"]["expected_agenda"] = ["Different answer key"]
                    final = next(event for event in bundle["trace"] if event["event"] == "run_finished")
                    final.update(agenda=bundle["fixture"]["expected_agenda"],
                                 slots=fixture["expected_slots"], error_type=error,
                                 status="error" if error else "completed")
                    sent = next(event for event in bundle["trace"] if event["event"] == "send_result")
                    sent["usage"]["input_tokens"] = 10
                    directory.mkdir()
                    (directory / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
                    return {**{key: final[key] for key in ("status", "error_type", "agenda", "slots")},
                            "reset": {"bindings_after": 1 if case == "reset" else 0,
                                      "conversation_cleared": True, "audit_preserved": True}}

                if case == "interrupt":
                    with self.assertRaises(KeyboardInterrupt):
                        run_plan(plan, root, execute)
                else:
                    run_plan(plan, root, execute, max_retries=1 if case == "retry" else 0,
                             retryable_errors=("transport_error",))
                report = score_directory(root)
                summary = report["summary"]
                self.assertEqual(summary["planned_attempts"], 1)
                self.assertEqual(summary["completion_rate"], 1.0 if case == "retry" else 0.0)
                self.assertEqual(summary["metrics"]["input_tokens"], 20 if case == "retry" else 10)
                if case == "retry":
                    self.assertEqual(summary["errors"], {})
                    self.assertEqual(summary["execution_errors"], {"transport_error": 1})
                else:
                    reasons = {"reset": "attempt_reset_failed", "interrupt": "runner_interrupted",
                               "changed_fixture": "bundle_plan_mismatch"}
                    self.assertEqual(summary["errors"], {reasons[case]: 1})
                    self.assertTrue(report["attempts"][0]["evidence_path"].endswith("bundle.json"))
if __name__ == "__main__":
    unittest.main()
