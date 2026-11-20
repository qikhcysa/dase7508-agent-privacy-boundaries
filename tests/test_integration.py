"""Verify the Issue #20 smoke path against the shared v1 contract."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from agent_privacy.hosted import run_agent
from agent_privacy.hosted_config import HostedConfig
from agent_privacy.integration import run_smoke
from agent_privacy.redaction import RULE_VERSION
from contracts.validate import load_json, validate
from member_a.agent_core.transport import TransportError
from tests.test_handoff import SummaryModel
from tests.test_hosted import SyntheticModel, call, reply


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(TemporaryDirectory()))
        self.config = HostedConfig(api_key="synthetic_offline_smoke_key")

    def test_all_conditions_use_one_fixture_and_share_one_frozen_h1_snapshot(self):
        root = self.folder / "matrix"
        summary_model = SummaryModel()
        controller_count = 0

        def controller_factory():
            nonlocal controller_count
            controller_count += 1
            return SyntheticModel()

        report = run_smoke(self.config, root, controller_factory=controller_factory,
                           summary_transport=summary_model)
        self.assertEqual(controller_count, 16)
        self.assertEqual(len(summary_model.requests), 1)
        self.assertEqual(report, load_json(root / "score.json"))
        self.assertEqual(report["summary"]["planned_attempts"], 16)
        self.assertEqual(report["summary"]["completed_attempts"], 16)
        self.assertEqual(report["summary"]["invalid_evidence"], [])

        ledger = load_json(root / "run-ledger.json")
        self.assertEqual(len(ledger["snapshots"]), 1)
        snapshot, = ledger["snapshots"]
        self.assertEqual(snapshot["generation_metrics"]["input_tokens"], 20)
        attempt_ids, conditions, snapshot_hashes = set(), set(), set()
        expected_reason = {"S0": "s0_instruction_only", "S1": RULE_VERSION,
                           "S2": "s2_allowlisted", "S3": "s3_context_authorized"}
        expected_local_reason = {**expected_reason, "S1": "s1_redaction_at_egress"}
        for record in ledger["attempts"]:
            execution, = record["executions"]
            planned = record["condition"]
            bundle = load_json(root / execution["bundle_path"])
            validate("bundle", bundle)
            run = bundle["run"]
            attempt_ids.add(run["attempt_id"])
            conditions.add((run["policy"], run["handoff"], run["fault"]))
            self.assertEqual(run["document_variant"], "benign")
            self.assertTrue(execution["reset_ok"])
            first_gate = next(event for event in bundle["trace"] if event["event"] == "egress_decision")
            self.assertEqual(first_gate["reason"], expected_reason[planned["policy"]])
            local_decisions = [event for event in bundle["trace"] if event["event"] == "policy_decision"]
            self.assertEqual({event["operation"] for event in local_decisions}, {"release", "load"})
            self.assertTrue(all(event["allowed"] for event in local_decisions))
            self.assertEqual({event["reason"] for event in local_decisions},
                             {expected_local_reason[planned["policy"]]})
            self.assertTrue(load_json(root / execution["outcome_path"])["valid_evidence"])
            if planned["handoff"] == "H1":
                snapshot_hashes.add(execution["snapshot_sha256"])
            if planned["fault"] == "F1":
                self.assertTrue(any(record["meta"]["producer"] == "minimal_scheduler"
                                    for record in bundle["objects"]))

        self.assertEqual(len(conditions), 16)
        self.assertEqual(len(attempt_ids), 16)
        self.assertEqual(snapshot_hashes, {snapshot["sha256"]})

    def test_denied_release_never_reaches_either_recipient_for_s2_or_s3(self):
        for policy in ("S2", "S3"):
            for recipient in ("controller", "mock_cloud"):
                with self.subTest(policy=policy, recipient=recipient):
                    output = self.folder / f"{policy}-{recipient}"

                    def request_blocked_field(payload, _step):
                        catalog = json.loads(payload["messages"][1]["content"].split("Asset catalog: ")[1])
                        handle = next(item["handle"] for item in catalog if item["kind"] == "private_calendar")
                        return reply({"role": "assistant", "content": None, "tool_calls": [
                            call("check_private_boundary", "release",
                                 {"handle": handle, "fields": ["events"], "recipient": recipient}),
                        ]})

                    controller = SyntheticModel(request_blocked_field)
                    result = run_agent(self.config, output_dir=output, policy=policy, transport=controller)
                    bundle = load_json(output / "bundle.json")
                    validate("bundle", bundle)
                    self.assertEqual(result["status"], "error")
                    self.assertEqual(len(controller.requests), 1)
                    events = bundle["trace"]
                    release_denial, = [event for event in events if event["event"] == "policy_decision"
                                       and event["operation"] == "release" and not event["allowed"]]
                    self.assertEqual(release_denial["reason"], result["error_type"])
                    self.assertEqual(sum(event["event"] == "send_attempt" for event in events), 1)
                    self.assertFalse(any(event["event"] in {"context_loaded", "receiver_record"}
                                         for event in events))

    def test_api_transport_failure_is_written_as_unknown_delivery(self):
        def failed_send(_payload, _step):
            raise TransportError("synthetic redacted diagnostic")

        output = self.folder / "api-failure"
        result = run_agent(self.config, output_dir=output, policy="S1",
                           transport=SyntheticModel(failed_send))
        bundle = load_json(output / "bundle.json")
        validate("bundle", bundle)
        self.assertEqual((result["status"], result["error_type"]), ("error", "transport_error"))
        send, = [event for event in bundle["trace"] if event["event"] == "send_result"]
        self.assertEqual(send["delivery"], "delivery_unknown")
        self.assertNotIn("synthetic redacted diagnostic", json.dumps(bundle))
