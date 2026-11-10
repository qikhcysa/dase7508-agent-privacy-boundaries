"""Acceptance evidence for the fixed S1 phone comparator."""

import base64
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from agent_privacy.egress import EgressAdapter
from agent_privacy.redaction import PHONE_REPLACEMENT, redact_value, redact_payload
from agent_privacy.scoped_registry import ScopedRegistry
from contracts.validate import ROOT, load_json, validate
from member_a.agent_core.transport import HttpTransport, ScriptedTransport


class PhoneRulesTests(unittest.TestCase):
    def test_fixed_formats_and_boundaries(self):
        for phone in ("87654321", "+85287654321", "852 87654321", "+852 87654321",
                      "852" + chr(45) + "87654321"):
            with self.subTest(phone=phone):
                self.assertEqual(redact_value(phone), PHONE_REPLACEMENT)
        for text in ("187654321", "13800138000", "8765 4321", "八七六五四三二一"):
            self.assertEqual(redact_value(text), text)

    def test_nested_data_is_copied_and_slots_preserved(self):
        original = {"phone": "87654321", "entries": [{"note": "Call 87654321"}],
                    "slots": [{"start": "2026" + chr(45) + "11" + chr(45) + "02T09:00:00+08:00"}],
                    "count": 8, "allowed": True, "empty": None}
        snapshot = deepcopy(original)
        result = redact_value(original)
        self.assertEqual(result["phone"], PHONE_REPLACEMENT)
        self.assertEqual(result["entries"][0]["note"], "Call " + PHONE_REPLACEMENT)
        self.assertEqual(result["slots"], original["slots"])
        self.assertEqual(original, snapshot)
        result["slots"].clear()
        self.assertEqual(original, snapshot)

    def test_content_json_is_decoded_but_protocol_identifiers_stay_intact(self):
        escaped = ''.join('\\u00' + format(ord(c), '02x') for c in "87654321")
        payload = {"model": "model87654321", "messages": [
            {"role": "tool", "tool_call_id": "call87654321", "content": '{"phone":"' + escaped + '"}'},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call87654321", "type": "function", "function": {
                    "name": "release", "arguments": '{"handle":"asset87654321","fields":["phone"]}'}},
                {"id": "save87654321", "type": "function", "function": {
                    "name": "save_memory", "arguments": '{"content":"call 87654321"}'}}]},
            {"role": "user", "content": [{"type": "text", "text": "87654321"}]}]}
        original = deepcopy(payload)
        result = redact_payload(payload, "controller")
        self.assertEqual(json.loads(result["messages"][0]["content"])["phone"], PHONE_REPLACEMENT)
        self.assertEqual(result["messages"][0]["tool_call_id"], "call87654321")
        calls = result["messages"][1]["tool_calls"]
        self.assertEqual(calls[0], original["messages"][1]["tool_calls"][0])
        self.assertEqual(json.loads(calls[1]["function"]["arguments"])["content"], "call " + PHONE_REPLACEMENT)
        self.assertEqual(result["messages"][2]["content"][0]["text"], PHONE_REPLACEMENT)
        self.assertEqual(result["model"], original["model"])
        self.assertEqual(payload, original)

    def test_cloud_only_transforms_selected_values(self):
        payload = {"handle": "asset87654321", "task_id": "task87654321",
                   "purpose": "meeting_scheduling", "fields": {"phone": "87654321"}}
        result = redact_payload(payload, "mock_cloud")
        self.assertEqual(result["fields"]["phone"], PHONE_REPLACEMENT)
        self.assertEqual(result["handle"], payload["handle"])
        self.assertEqual(result["task_id"], payload["task_id"])

    def test_limitations_are_observable_without_special_fixture_rules(self):
        data = {"title": "SYNTHETIC_PRIVATE_EVENT", "location": "Synthetic Room",
                "phone": "SYNTHETIC_PHONE_555_0100", "reference": "12345678"}
        result = redact_value(data)
        self.assertEqual(result["title"], data["title"])
        self.assertEqual(result["phone"], data["phone"])
        self.assertEqual(result["reference"], PHONE_REPLACEMENT)

    def test_unsupported_content_fails_instead_of_silently_bypassing(self):
        with self.assertRaises(ValueError):
            redact_payload({"messages": [{"role": "user", "content": [{"type": "image_url"}]}]}, "controller")
        with self.assertRaises(ValueError):
            redact_payload({"messages": [{"role": "assistant", "tool_calls": [
                {"function": {"name": "save_memory", "arguments": "invalid"}}]}]}, "controller")


class S1EgressTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        self.bundle = load_json(ROOT / "examples" / "benign-h0.json")
        self.bundle["run"]["policy"] = "S1"
        self.bundle["objects"][2]["value"]["entries"][0]["phone"] = "+852 87654321"
        self.registry = self.enterContext(ScopedRegistry())
        for record in self.bundle["objects"]:
            self.registry.put_record(record)

    def adapter(self, controller, name="attempt"):
        return EgressAdapter(self.bundle["run"], self.registry, controller=controller,
                             trace_path=self.directory / (name + ".jsonl"))

    def trace(self, adapter):
        bundle = deepcopy(self.bundle)
        bundle["trace"] = [json.loads(line) for line in adapter.trace_path.read_text(encoding="utf8").splitlines()]
        validate("bundle", bundle)
        return bundle["trace"]

    def test_both_recipients_and_fault_inputs_have_exact_redacted_bytes(self):
        observed = []
        active = None

        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                recorded = json.loads(active.trace_path.read_text(encoding="utf8").splitlines()[-1])
                observed.append((body, recorded))
                response = b'{}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, *_args):
                pass

        with HTTPServer(("127.0.0.1", 0), Receiver) as server:
            thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            thread.start()
            try:
                for fault in ("F0", "F1"):
                    self.bundle["run"]["fault"] = fault
                    self.bundle["run"]["controller"].update(mode="hosted", model="synthetic_model")
                    active = self.adapter(HttpTransport(f"http://127.0.0.1:{server.server_port}/"), fault)
                    selection = {"handle": "contacts.organizer", "fields": ["entries"]}
                    value = self.registry.inspect_record("contacts.organizer")["value"]
                    payload = {"model": "synthetic_model", "messages": [{"role": "user", "content": json.dumps(value)}]}
                    snapshot = deepcopy(payload)
                    active.send_controller(payload, selections=[selection])
                    for call, handle, fields in (("phone", "contacts.organizer", ["entries"]),
                                                 ("slots", "schedule.slots", ["slots"])):
                        active.record_proposal(call, {"proposal_id": call, "name": "release", "arguments": {
                            "handle": handle, "fields": fields, "recipient": "mock_cloud"}})
                        active.release_to_cloud(call)
                    events = self.trace(active)
                    sends = [e for e in events if e["event"] == "send_attempt"]
                    receipts = [e for e in events if e["event"] == "receiver_record"]
                    self.assertEqual(len(sends), 3)
                    self.assertEqual(len(receipts), 2)
                    for send in sends[:2]:
                        body = base64.b64decode(send["body"]["base64"])
                        self.assertNotIn(b"87654321", body)
                        self.assertIn(PHONE_REPLACEMENT.encode(), body)
                    self.assertEqual(observed[-1][0], base64.b64decode(sends[0]["body"]["base64"]))
                    self.assertEqual(observed[-1][1], sends[0])
                    self.assertEqual(sends[1]["body"], receipts[0]["body"])
                    sent_slots = json.loads(base64.b64decode(sends[2]["body"]["base64"]))["fields"]["slots"]
                    self.assertEqual(sent_slots, self.bundle["objects"][3]["value"]["slots"])
                    self.assertTrue(all(e["reason"] == "s1_phone_v1" for e in events if e["event"] == "egress_decision"))
                    self.assertEqual(payload, snapshot)
                    self.assertEqual(self.registry.inspect_record("contacts.organizer")["value"], value)
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual(len(observed), 2)

    def test_repeat_messages_are_redacted_again_and_s0_is_unchanged(self):
        payload = {"messages": [{"role": "user", "content": "phone 87654321"}]}
        controller = ScriptedTransport([{}, {}])
        adapter = self.adapter(controller)
        adapter.send_controller(payload, selections=[])
        adapter.send_controller(payload, selections=[])
        self.assertTrue(all(b"87654321" not in body for body in controller.requests))
        self.trace(adapter)
        self.bundle["run"]["policy"] = "S0"
        original = ScriptedTransport([{}])
        baseline = self.adapter(original, "baseline")
        baseline.send_controller(payload, selections=[])
        self.assertIn(b"87654321", original.requests[0])
        self.trace(baseline)

    def test_record_failure_stops_s1_send(self):
        controller = ScriptedTransport([{}])
        adapter = self.adapter(controller)
        record = adapter._record

        def fail(event, **fields):
            if event == "send_attempt":
                raise OSError("audit unavailable")
            record(event, **fields)

        with patch.object(adapter, "_record", side_effect=fail):
            with self.assertRaises(OSError):
                adapter.send_controller({"messages": [{"role": "user", "content": "87654321"}]}, selections=[])
        self.assertEqual(controller.requests, [])
        self.trace(adapter)


if __name__ == "__main__":
    unittest.main()
