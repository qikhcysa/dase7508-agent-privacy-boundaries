import json
from pathlib import Path
import shutil
import tempfile
import unittest

from agent_privacy.handoff import prepare_handoff
from agent_privacy.hosted import run_agent
from agent_privacy.hosted_config import HostedConfig
from agent_privacy.runner import (
    RunnerError,
    build_core_plan,
    plan_sha256,
    run_plan,
    validate_plan,
)
from agent_privacy.scorer import score_directory
from tests.test_handoff import SummaryModel, summary_reply
from tests.test_hosted_h1 import MobileModel


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "benign" / "B01.json"
EXAMPLE = ROOT / "contracts" / "examples" / "benign-h0.json"


class RunnerPlanTests(unittest.TestCase):
    def test_default_core_matrix_has_all_1152_attempts(self):
        plan = build_core_plan(seed="test-seed")
        validate_plan(plan)
        self.assertEqual(plan["block_count"], 36)
        self.assertEqual(plan["attempt_count"], 1152)
        self.assertTrue(all(len(block["attempts"]) == 32 for block in plan["blocks"]))
        keys = [attempt["attempt_key"] for block in plan["blocks"] for attempt in block["attempts"]]
        self.assertEqual(len(keys), len(set(keys)))

    def test_order_is_reproducible_and_seeded_within_blocks(self):
        first = build_core_plan([FIXTURE], repetitions=1, seed="same")
        again = build_core_plan([FIXTURE], repetitions=1, seed="same")
        other = build_core_plan([FIXTURE], repetitions=1, seed="other")
        self.assertEqual(first, again)
        self.assertEqual(plan_sha256(first), plan_sha256(again))
        self.assertNotEqual(
            [item["attempt_key"] for item in first["blocks"][0]["attempts"]],
            [item["attempt_key"] for item in other["blocks"][0]["attempts"]],
        )
        self.assertEqual(
            {item["attempt_key"] for item in first["blocks"][0]["attempts"]},
            {item["attempt_key"] for item in other["blocks"][0]["attempts"]},
        )

    def test_h1_snapshot_key_is_shared_only_across_policy_and_fault(self):
        plan = build_core_plan([FIXTURE], repetitions=1)
        h1 = [item for item in plan["blocks"][0]["attempts"] if item["handoff"] == "H1"]
        grouped = {}
        for item in h1:
            grouped.setdefault(item["document_variant"], set()).add(item["handoff_snapshot_key"])
        self.assertEqual({name: len(keys) for name, keys in grouped.items()}, {"benign": 1, "attacked": 1})
        self.assertNotEqual(*[next(iter(grouped[name])) for name in sorted(grouped)])

    def test_changed_fixture_bytes_fail_validation(self):
        plan = build_core_plan([FIXTURE], repetitions=1)
        plan["fixtures"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RunnerError, "fixture_bytes_changed"):
            validate_plan(plan)


class RunnerExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def one_plan(self, **dimensions):
        values = dict(
            fixture_paths=[FIXTURE], repetitions=1, policies=("S0",),
            handoffs=("H0",), faults=("F0",), document_variants=("benign",),
        )
        values.update(dimensions)
        return build_core_plan(**values)

    @staticmethod
    def result(status="completed", error_type=None, reset=True):
        return {
            "status": status,
            "error_type": error_type,
            "agenda": [],
            "slots": [],
            "reset": {
                "bindings_after": 0 if reset else 1,
                "conversation_cleared": reset,
                "audit_preserved": True,
            },
        }

    def test_retries_are_explicit_and_every_try_is_retained(self):
        calls = 0

        def executor(_condition, directory, _snapshot):
            nonlocal calls
            calls += 1
            directory.mkdir()
            shutil.copyfile(EXAMPLE, directory / "bundle.json")
            if calls == 1:
                return self.result("error", "transport_error")
            return self.result()

        ledger = run_plan(
            self.one_plan(), self.root / "run", executor,
            max_retries=1, retryable_errors=("transport_error",),
        )
        executions = ledger["attempts"][0]["executions"]
        self.assertEqual([item["status"] for item in executions], ["error", "completed"])
        self.assertEqual(ledger["attempts"][0]["selected_try"], 2)
        self.assertTrue(all((self.root / "run" / item["result_path"]).is_file() for item in executions))
        self.assertTrue(all(item["metrics"]["send_count"] > 0 for item in executions))
        saved = json.loads((self.root / "run" / "run-ledger.json").read_text(encoding="utf-8"))
        self.assertIsNotNone(saved["finished_at"])

    def test_checkpoint_resume_keeps_prefix_and_metadata(self):
        plan = self.one_plan(policies=("S0", "S1"))
        calls = []

        def executor(condition, directory, _snapshot):
            calls.append(condition["attempt_key"])
            directory.mkdir()
            return self.result()

        root = self.root / "resumable"
        metadata = {"phase": "formal", "protocol_sha256": "a" * 64}
        first = run_plan(plan, root, executor, max_new_conditions=1, metadata=metadata)
        self.assertEqual(len(first["attempts"]), 1)
        self.assertIsNone(first["finished_at"])
        resumed = run_plan(plan, root, executor, resume=True, max_new_conditions=1,
                           metadata=metadata)
        self.assertEqual(len(resumed["attempts"]), 2)
        self.assertIsNotNone(resumed["finished_at"])
        self.assertEqual(calls, [item["attempt_key"] for item in plan["blocks"][0]["attempts"]])
        with self.assertRaisesRegex(RunnerError, "resume_ledger_changed"):
            run_plan(plan, root, executor, resume=True, metadata={"phase": "changed"})

    def test_failed_reset_turns_a_completed_executor_into_an_error(self):
        def executor(_condition, directory, _snapshot):
            directory.mkdir()
            return self.result(reset=False)

        ledger = run_plan(self.one_plan(), self.root / "run", executor)
        execution = ledger["attempts"][0]["executions"][0]
        self.assertEqual(execution["status"], "error")
        self.assertEqual(execution["error_type"], "attempt_reset_failed")
        self.assertFalse(execution["reset_ok"])

    def test_restart_preserves_unresolved_reset_stop(self):
        plan = self.one_plan(policies=("S0", "S1"))
        root = self.root / "reset-stop"
        calls = []

        def executor(condition, directory, _snapshot):
            calls.append(condition["attempt_key"])
            directory.mkdir()
            return self.result(reset=False)

        def stop_on_failed_reset(record):
            if not record["executions"][0]["reset_ok"]:
                raise ValueError("review reset")

        with self.assertRaisesRegex(ValueError, "review reset"):
            run_plan(plan, root, executor, after_condition=stop_on_failed_reset)
        ledger_path = root / "run-ledger.json"
        before = ledger_path.read_bytes()
        with self.assertRaisesRegex(RunnerError, "resume_requires_evidence_review"):
            run_plan(plan, root, executor, after_condition=stop_on_failed_reset, resume=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(ledger_path.read_bytes(), before)
        self.assertIsNone(json.loads(before)["finished_at"])

    def test_h1_snapshot_is_prepared_once_and_reused_immutably(self):
        plan = self.one_plan(handoffs=("H1",), policies=("S0", "S1"), faults=("F0", "F1"))
        provider_calls = 0

        def provider(_condition, directory):
            nonlocal provider_calls
            provider_calls += 1
            path = directory / "summary.json"
            path.write_text('{"summary":"fixed"}\n', encoding="utf-8")
            return path

        seen = []

        def executor(_condition, directory, snapshot):
            self.assertIsNotNone(snapshot)
            seen.append((snapshot, snapshot.read_bytes()))
            directory.mkdir()
            shutil.copyfile(snapshot, directory / "handoff-artifact.json")
            return self.result()

        ledger = run_plan(plan, self.root / "run", executor, snapshot_provider=provider)
        self.assertEqual(provider_calls, 1)
        self.assertEqual(len(ledger["snapshots"]), 1)
        self.assertEqual(len(seen), 4)
        self.assertEqual(len({path for path, _data in seen}), 1)
        self.assertEqual(len({data for _path, data in seen}), 1)
        hashes = {
            execution["snapshot_sha256"]
            for attempt in ledger["attempts"] for execution in attempt["executions"]
        }
        self.assertEqual(len(hashes), 1)

    def test_snapshot_mutation_is_recorded_as_failure(self):
        plan = self.one_plan(handoffs=("H1",))
        calls = 0

        def provider(_condition, directory):
            path = directory / "summary.json"
            path.write_text("fixed", encoding="utf-8")
            return path

        def executor(_condition, directory, snapshot):
            nonlocal calls
            calls += 1
            directory.mkdir()
            snapshot.write_text("changed", encoding="utf-8")
            return self.result()

        ledger = run_plan(plan, self.root / "run", executor, snapshot_provider=provider,
                          max_retries=1, retryable_errors=("h1_snapshot_changed",))
        execution = ledger["attempts"][0]["executions"][0]
        self.assertEqual(calls, 1)
        self.assertEqual(execution["status"], "error")
        self.assertEqual(execution["error_type"], "h1_snapshot_changed")

    def test_deleted_snapshot_does_not_abort_the_ledger(self):
        plan = self.one_plan(handoffs=("H1",), policies=("S0", "S1"))

        def provider(_condition, directory):
            path = directory / "snapshot.json"
            path.write_text("frozen", encoding="utf-8")
            return path

        def executor(_condition, directory, snapshot):
            directory.mkdir()
            snapshot.unlink()
            return self.result()

        root = self.root / "run"
        ledger = run_plan(plan, root, executor, snapshot_provider=provider)
        first, second = ledger["attempts"]
        self.assertIsNotNone(ledger["finished_at"])
        self.assertEqual(first["executions"][0]["error_type"], "h1_snapshot_missing")
        self.assertEqual(second["preparation_error"], "h1_snapshot_missing")
        self.assertEqual(score_directory(root)["summary"]["errors"], {"h1_snapshot_missing": 2})

    def test_snapshot_provider_failure_is_retained_without_an_implicit_retry(self):
        plan = self.one_plan(handoffs=("H1",), policies=("S0", "S1"))
        calls = 0

        def provider(_condition, _directory):
            nonlocal calls
            calls += 1
            raise RuntimeError("untrusted provider text must not enter the ledger")

        ledger = run_plan(
            plan, self.root / "run", lambda *_args: self.fail("executor must not run"),
            snapshot_provider=provider,
        )
        self.assertEqual(calls, 1)
        self.assertEqual(ledger["snapshots"][0]["error_type"], "snapshot_provider_RuntimeError")
        self.assertTrue(all(
            attempt["preparation_error"] == "snapshot_provider_RuntimeError"
            and attempt["executions"] == []
            for attempt in ledger["attempts"]
        ))
        self.assertIsNotNone(ledger["finished_at"])

    def test_generation_usage_and_hosted_snapshot_copy_reach_the_score_report(self):
        fixture = ROOT / "fixtures" / "t01.json"
        plan = self.one_plan(fixture_paths=[fixture], handoffs=("H1",), faults=("F0", "F1"))
        config = HostedConfig(api_key="synthetic_evaluation_test_key")
        for case in ("valid", "wrong_copy", "failed_generation", "legacy_failed_generation"):
            with self.subTest(case=case):
                root = self.root / case
                failed = case.endswith("failed_generation")
                reply = summary_reply(finish="length" if failed else "stop")
                model = SummaryModel(response=reply)

                def provider(_condition, directory):
                    cache_dir = directory.parent if case == "legacy_failed_generation" else directory
                    artifact = prepare_handoff(config, fixture_path=fixture, cache_dir=cache_dir,
                                               transport=model)
                    # Archived snapshots can have different JSON formatting.
                    artifact.write_bytes(artifact.read_bytes() + b" ")
                    return artifact

                def executor(condition, directory, snapshot):
                    result = run_agent(config, fixture_path=fixture, handoff_path=snapshot,
                                       output_dir=directory, transport=MobileModel(),
                                       fault=condition["fault"])
                    if case == "wrong_copy":
                        artifact = directory / "handoff-artifact.json"
                        artifact.write_bytes(artifact.read_bytes() + b" ")
                    return result

                ledger = run_plan(plan, root, executor, snapshot_provider=provider)
                snapshot = ledger["snapshots"][0]
                if case == "legacy_failed_generation":
                    for field in ("generation_bundle_paths", "generation_observations",
                                  "generation_error_type"):
                        del snapshot[field]
                    (root / "run-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
                else:
                    self.assertTrue(snapshot["generation_bundle_path"])
                report = score_directory(root)
                self.assertEqual(len(model.requests), 1)
                self.assertEqual(report["summary"]["metrics"]["input_tokens"], 20)
                if failed:
                    self.assertEqual(report["summary"]["metrics"]["send_count"], 1)
                if case == "valid":
                    self.assertEqual(report["summary"]["scored_attempts"], 2)
                    self.assertEqual(report["summary"]["errors"], {})
                elif case == "wrong_copy":
                    self.assertEqual(report["summary"]["scored_attempts"], 0)
                    self.assertEqual(report["summary"]["errors"], {"h1_snapshot_use_mismatch": 2})
                else:
                    self.assertEqual(report["summary"]["scored_attempts"], 0)
                    self.assertEqual(report["summary"]["snapshot_generation_errors"],
                                     {"snapshot_provider_HandoffError": 1})

    def test_h1_requires_provider_before_output_is_created(self):
        output = self.root / "run"
        with self.assertRaisesRegex(RunnerError, "h1_snapshot_provider_required"):
            run_plan(self.one_plan(handoffs=("H1",)), output, lambda *_args: None)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
