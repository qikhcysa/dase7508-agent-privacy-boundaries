"""Verify the Issue #20 smoke path against the shared v1 contract."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import UUID

from agent_privacy.handoff import prepare_handoff
from agent_privacy.hosted import ROOT, run_agent
from agent_privacy.hosted_config import HostedConfig
from agent_privacy.integration import run_smoke
from agent_privacy.redaction import PHONE_REPLACEMENT, RULE_VERSION
from contracts.validate import load_json, validate
from member_a.agent_core.transport import TransportError
from tests.test_handoff import SUMMARY, SummaryModel, summary_reply
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

    def test_s1_preserves_generated_handles_and_redacts_document_text(self):
        phone = "+852 00000000"
        fixture = load_json(ROOT / "fixtures" / "t01.json")
        fixture["benign_paragraph"] += f" Synthetic callback number: {phone}."
        fixture_path = self.folder / "benign-phone.json"
        fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
        output = self.folder / "s1-number-like-handles"
        controller = SyntheticModel()
        # A valid generated identifier can contain an isolated eight-digit sequence.
        identifiers = [UUID(f"12345678-aaaa-4abc-bdef-{index:012x}") for index in range(1, 7)]
        with patch("agent_privacy.scoped_registry.uuid4", side_effect=identifiers):
            result = run_agent(self.config, fixture_path=fixture_path, output_dir=output,
                               policy="S1", transport=controller)
        self.assertEqual((result["status"], result["error_type"]), ("completed", None))

        bundle = load_json(output / "bundle.json")
        validate("bundle", bundle)
        handles = {record["meta"]["source"]: record["handle"] for record in bundle["objects"]}
        document_handle = handles["meeting_document"]
        slots_handle = handles["local_tool"]
        self.assertIn("12345678", document_handle)
        self.assertIn("12345678", slots_handle)
        catalog = controller.requests[0]["messages"][1]["content"].split("Asset catalog: ")[1]
        self.assertEqual(json.loads(catalog)[0]["handle"], document_handle)

        document_result = json.loads(controller.requests[1]["messages"][-1]["content"])
        self.assertEqual(document_result["handle"], document_handle)
        self.assertEqual(document_result["value"]["text"],
                         fixture["document_common"] + "\n\n" +
                         fixture["benign_paragraph"].replace(phone, PHONE_REPLACEMENT))
        schedule_result = json.loads(controller.requests[2]["messages"][-1]["content"])
        self.assertEqual(schedule_result, {"handle": slots_handle, "slots": fixture["expected_slots"]})

    def test_s1_mobile_summary_keeps_registered_lineage_and_redacts_text(self):
        phone = "+852 00000000"
        summary_text = f"{SUMMARY} Synthetic callback number: {phone}."
        output = self.folder / "s1-mobile-summary"
        controller = SyntheticModel()
        identifiers = (UUID(f"12345678-aaaa-4abc-bdef-{index:012x}") for index in range(1, 16))
        with patch("agent_privacy.scoped_registry.uuid4", side_effect=identifiers):
            artifact = prepare_handoff(
                self.config, cache_dir=self.folder / "handoff",
                transport=SummaryModel(summary_reply(summary_text)),
            )
            result = run_agent(self.config, output_dir=output, handoff_path=artifact,
                               policy="S1", transport=controller)
        self.assertEqual((result["status"], result["error_type"]), ("completed", None))

        bundle = load_json(output / "bundle.json")
        validate("bundle", bundle)
        summary_handle = bundle["handoff"]["summary_handle"]
        summary = next(obj for obj in bundle["objects"] if obj["handle"] == summary_handle)
        parent, = summary["meta"]["derivation"]
        self.assertIn("12345678", summary_handle)
        self.assertIn("12345678", parent)
        for request in controller.requests[1:]:
            release = next(message for message in request["messages"]
                           if message.get("tool_call_id") == "read_document")
            content = json.loads(release["content"])
            self.assertEqual(content["handle"], summary_handle)
            self.assertEqual(content["source_metadata"]["derivation"], [parent])
            self.assertEqual(content["value"]["text"], summary_text.replace(phone, PHONE_REPLACEMENT))

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
