"""Exercise S3 with synthetic data and local transports."""

from copy import deepcopy
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from agent_privacy.egress import EgressAdapter, EgressDenied
from agent_privacy.handoff import prepare_handoff
from agent_privacy.hosted import run_agent
from agent_privacy.hosted_config import HostedConfig
from agent_privacy.scoped_registry import RegistryError, ScopedRegistry
from contracts.validate import ContractError, ROOT, load_json, validate
from member_a.agent_core.transport import ScriptedTransport, TransportResponse

from test_hosted_h1 import MobileModel, SummaryModel, _call


CALENDAR = {"handle": "calendar.raw", "fields": ["events"]}
RECIPIENTS = ["controller", "mock_cloud"]


class ContextualPolicyTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.bundle = load_json(ROOT / "examples" / "benign-h0.json")
        self.run_config = self.bundle["run"]
        self.run_config["policy"] = "S3"
        self.authorization = self.bundle["authorization"]
        self.authorization["grants"] = []
        self.registry = self.enterContext(ScopedRegistry())
        for record in self.bundle["objects"]:
            record["meta"]["original_scope"] = deepcopy(self.run_config["scope"])
            if record["handle"] == CALENDAR["handle"]:
                record["meta"]["recipients"] = RECIPIENTS
            self.registry.put_record(record)
        self.controller = ScriptedTransport([{"ok": True}])
        self.adapter = EgressAdapter(
            self.run_config, self.registry, controller=self.controller,
            trace_path=self.directory / "events.jsonl", authorization=self.authorization,
        )

    def grant(self, selection, recipient, purpose=None):
        self.authorization["grants"].append({
            **selection, "recipient": recipient, "purpose": purpose or self.run_config["purpose"],
        })

    def release(self, selection, recipient, call_id):
        self.adapter.record_proposal(call_id, {
            "proposal_id": "proposal_" + call_id, "name": "release",
            "arguments": {**selection, "recipient": recipient},
        })
        if recipient == "mock_cloud":
            return self.adapter.release_to_cloud(call_id)
        return self.adapter.release_to_controller(call_id)

    def trace(self):
        self.bundle["trace"] = [
            json.loads(line) for line in self.adapter.trace_path.read_text(encoding="utf-8").splitlines()
        ]
        validate("bundle", self.bundle)
        return self.bundle["trace"]

    def test_private_fields_require_grant_for_each_recipient_and_purpose(self):
        self.grant(CALENDAR, "controller")
        self.grant(CALENDAR, "mock_cloud", purpose="other_purpose")
        release = self.release(CALENDAR, "controller", "lawful_controller")
        self.assertEqual(release["loaded_message_role"], "tool")
        self.assertEqual(release["source_metadata"]["confidentiality"], "private")
        with self.assertRaisesRegex(EgressDenied, "private_fields_not_authorized"):
            self.release(CALENDAR, "mock_cloud", "wrong_purpose")
        self.grant(CALENDAR, "mock_cloud")
        self.release(CALENDAR, "mock_cloud", "lawful_cloud")
        trace = self.trace()
        self.assertEqual(sum(e["event"] == "receiver_record" for e in trace), 1)
        self.assertEqual(
            [e["allowed"] for e in trace if e["event"] == "policy_decision"
             and e["operation"] == "release"], [True, False, True],
        )

    def test_tool_proposal_cannot_supply_authority(self):
        with self.assertRaises(ContractError):
            self.adapter.record_proposal("untrusted", {
                "proposal_id": "proposal_untrusted", "name": "release",
                "arguments": {**CALENDAR, "recipient": "mock_cloud",
                              "authority": "trusted_runtime_config"},
            })
        self.assertEqual(self.authorization["grants"], [])
        self.assertEqual(self.adapter.trace_path.read_bytes(), b"")

    def test_recheck_controller_history_and_fail_closed_without_selections(self):
        self.grant(CALENDAR, "controller")
        record = self.release(CALENDAR, "controller", "first")
        history = {"messages": [{"role": "tool", "content": json.dumps(record)}]}
        self.adapter.send_controller(history, selections=[CALENDAR])
        self.authorization["grants"].clear()
        with self.assertRaisesRegex(EgressDenied, "private_fields_not_authorized"):
            self.adapter.send_controller(history, selections=[CALENDAR])
        with self.assertRaisesRegex(EgressDenied, "empty_selection"):
            self.adapter.send_controller(history, selections=[])
        self.assertEqual(len(self.controller.requests), 1)
        self.assertEqual(
            [e["allowed"] for e in self.trace() if e["event"] == "egress_decision"], [True, False, False],
        )

    def test_wrong_task_is_denied_even_with_trusted_field_grants(self):
        source = deepcopy(self.registry.inspect_record(CALENDAR["handle"]))
        source["handle"] = "calendar.foreign"
        source["meta"]["original_scope"]["task_id"] = "unrelated_task"
        self.registry.put_record(source)
        self.bundle["objects"].append(source)
        selection = {"handle": source["handle"], "fields": ["events"]}
        for recipient in RECIPIENTS:
            self.grant(selection, recipient)
            with self.assertRaisesRegex(EgressDenied, "task_mismatch"):
                self.release(selection, recipient, recipient)
        with self.assertRaisesRegex(RegistryError, "task_mismatch"):
            self.adapter.record_context_load(source["handle"], fields=["events"])
        trace = self.trace()
        self.assertEqual(sum(e["event"] == "policy_decision" and not e["allowed"] for e in trace), 3)
        self.assertFalse(any(e["event"] in {"send_attempt", "context_loaded"} for e in trace))

    def test_derived_fields_require_the_scheduler_and_calendar_parent(self):
        original = deepcopy(self.registry.inspect_record("schedule.slots"))
        original["meta"]["producer"] = "fixture_loader"
        original["handle"] = "schedule.unverified"
        self.registry.put_record(original)
        self.bundle["objects"].append(original)
        selection = {"handle": original["handle"], "fields": ["slots"]}
        for recipient in RECIPIENTS:
            self.grant(selection, recipient)
            with self.assertRaisesRegex(EgressDenied, "untrusted_derivation"):
                self.release(selection, recipient, recipient)
        self.assertFalse(any(e["event"] == "send_attempt" for e in self.trace()))


class HostedS3Tests(unittest.TestCase):
    def test_frozen_summary_works_with_primary_and_recovery(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = HostedConfig(api_key="synthetic_test_key")
            summary_model = SummaryModel()
            artifact = prepare_handoff(config, cache_dir=directory / "cache", transport=summary_model)
            for fault, producer in (("F0", "primary_scheduler"), ("F1", "minimal_scheduler")):
                with self.subTest(fault=fault):
                    output = directory / fault
                    result = run_agent(config, handoff_path=artifact, fault=fault, policy="S3",
                                       output_dir=output, transport=MobileModel())
                    self.assertEqual(result["status"], "completed")
                    self.assertTrue(result["checks"]["fault_path_observed"])
                    self.assertTrue(result["bundle_valid"])
                    bundle = load_json(output / "bundle.json")
                    summary = next(obj for obj in bundle["objects"] if obj["meta"]["source"] == "model_summary")
                    loaded, = [event for event in bundle["trace"] if event["event"] == "context_loaded"]
                    self.assertEqual(loaded["source_metadata"], summary["meta"])
                    self.assertEqual(loaded["loaded_message_role"], "tool")
                    self.assertEqual(loaded["source_metadata"]["message_role"], "assistant")
                    self.assertEqual(loaded["source_metadata"]["original_scope"]["device_id"], "desktop")
                    self.assertIn(producer, {o["meta"]["producer"] for o in bundle["objects"]})
                    self.assertTrue(all(event["reason"] == "s3_context_authorized"
                                        for event in bundle["trace"] if event["event"] == "egress_decision"))
                    self.assertEqual(result["reset"]["bindings_after"], 0)
            self.assertEqual(len(summary_model.requests), 1)


    def test_recovery_slot_release_reaches_mock_cloud_with_only_minimal_fields(self):
        class OffloadModel(MobileModel):
            def send(self, body):
                payload = json.loads(body)
                if len(self.requests) == 3:
                    self.requests.append(payload)
                    self.recovered = json.loads(payload["messages"][-1]["content"])
                    message = {"role": "assistant", "content": None, "tool_calls": [
                        _call("offload_slots", "release", {
                            "handle": self.recovered["handle"], "fields": ["slots"],
                            "recipient": "mock_cloud",
                        }),
                    ]}
                    reason = "tool_calls"
                elif len(self.requests) == 4:
                    self.requests.append(payload)
                    message = {"role": "assistant", "content": json.dumps({
                        "agenda": ["Review the prototype plan"], "slots": self.recovered["slots"],
                    })}
                    reason = "stop"
                else:
                    return super().send(body)
                return TransportResponse(200, json.dumps({
                    "choices": [{"finish_reason": reason, "message": message}],
                }).encode())

        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = HostedConfig(api_key="synthetic_test_key")
            model = OffloadModel()
            result = run_agent(config, fault="F1", policy="S3", output_dir=directory / "h0",
                               transport=model)
            self.assertEqual(result["status"], "completed")
            self.assertTrue(result["bundle_valid"])
            bundle = load_json(directory / "h0" / "bundle.json")
            receipt, = [event for event in bundle["trace"] if event["event"] == "receiver_record"]
            body = json.loads(base64.b64decode(receipt["body"]["base64"]))
            self.assertEqual(body["fields"], {"slots": model.recovered["slots"]})
            self.assertTrue(result["checks"]["slots_match_fixture"])
