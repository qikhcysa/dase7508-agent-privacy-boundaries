"""Contract and transport checks for the shared v1 egress path."""

import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from agent_privacy.egress import EgressAdapter, S0_PRIVACY_INSTRUCTION
from agent_privacy.scoped_registry import RegistryError, ScopedRegistry
from contracts.validate import ContractError, ROOT, load_json, validate
from member_a.agent_core.transport import HttpTransport, ScriptedTransport, TransportError, TransportResponse


def read_trace(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def recorded_bytes(evidence):
    return base64.b64decode(evidence["base64"])


class EgressTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        self.bundle = load_json(ROOT / "examples" / "benign-h0.json")
        self.bundle["run"]["policy"] = "S0"
        self.bundle["trace"] = []
        self.registry = self.enterContext(ScopedRegistry())
        for record in self.bundle["objects"]:
            self.registry.put_record(record)
        self.cloud_proposal = {
            "proposal_id": "proposal_cloud",
            "name": "release",
            "arguments": {"handle": "calendar.raw", "fields": ["events"], "recipient": "mock_cloud"},
        }
        self.payload = {"messages": [{"role": "user", "content": "会议安排"}]}

    def adapter(self, controller, name="attempt"):
        return EgressAdapter(self.bundle["run"], self.registry, controller=controller,
                             trace_path=self.directory / f"{name}.jsonl")

    def verified_trace(self, adapter):
        self.bundle["trace"] = read_trace(adapter.trace_path)
        validate("bundle", self.bundle)
        return self.bundle["trace"]

    def test_normal_and_fallback_send_exact_bytes_through_same_boundary(self):
        observed = []
        response_body = b'{ "provider": "loopback", "choices": [] }\n'
        active_trace = None

        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                request = self.rfile.read(int(self.headers["Content-Length"]))
                # Read from disk inside the receiver, before sending any response.
                observed.append((request, self.headers.get("Authorization"), read_trace(active_trace)[-1]))
                self.send_response(200)
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, *_args):
                pass

        with HTTPServer(("127.0.0.1", 0), Receiver) as server:
            thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            thread.start()
            try:
                self.bundle["run"]["controller"].update(mode="hosted", model="synthetic-model")
                for fault in ("F0", "F1"):
                    with self.subTest(fault=fault):
                        self.bundle["run"]["fault"] = fault
                        controller = HttpTransport(
                            f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                            api_key="synthetic_header_only", timeout=3,
                        )
                        adapter = self.adapter(controller, fault)
                        active_trace = adapter.trace_path
                        value = self.registry.inspect_record("calendar.raw")["value"]
                        payload = {"model": "synthetic-model", "messages": [
                            *self.payload["messages"],
                            {"role": "user", "content": json.dumps({"path": fault, "data": value})},
                        ]}
                        selection = [{"handle": "calendar.raw", "fields": ["events"]}]
                        self.assertEqual(adapter.send_controller(payload, selections=selection).body, response_body)
                        adapter.record_proposal("call_cloud", self.cloud_proposal)
                        self.assertEqual(adapter.release_to_cloud("call_cloud").status, 200)
                        events = self.verified_trace(adapter)
                        self.assertEqual([event["event"] for event in events], [
                            "egress_decision", "send_attempt", "send_result",
                            "tool_proposal", "release_request", "policy_decision",
                            "egress_decision", "send_attempt", "receiver_record", "send_result",
                        ])
                        request, authorization, before_post = observed[-1]
                        self.assertEqual(before_post, events[1])
                        self.assertEqual(request, recorded_bytes(events[1]["body"]))
                        self.assertEqual(authorization, "Bearer synthetic_header_only")
                        self.assertNotIn("synthetic_header_only", active_trace.read_text(encoding="utf-8"))
                        self.assertEqual(json.loads(request)["messages"][0],
                                         {"role": "system", "content": S0_PRIVACY_INSTRUCTION})
                        self.assertIn("会议安排".encode("utf-8"), request)
                        self.assertIn(b"SYNTHETIC_PRIVATE_EVENT", request)
                        self.assertEqual(events[2]["delivery"], "http_response_observed")
                        self.assertEqual(recorded_bytes(events[2]["response"]), response_body)
                        cloud_request = recorded_bytes(events[7]["body"])
                        self.assertIn(b"SYNTHETIC_PRIVATE_EVENT", cloud_request)
                        self.assertEqual(recorded_bytes(events[8]["body"]), cloud_request)
                        self.assertEqual(events[9]["delivery"], "mock_receipt_observed")
                        self.assertEqual(json.loads(recorded_bytes(events[9]["response"]))["sha256"],
                                         events[7]["body"]["sha256"])
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual(len(observed), 2)

    def test_failed_transport_records_unknown_delivery_without_retry(self):
        self.bundle["run"]["controller"].update(mode="hosted", model="synthetic-model")
        controller = HttpTransport("https://provider.example.invalid/v1/chat/completions")
        adapter = self.adapter(controller)
        with patch.object(controller, "send", side_effect=TransportError("timeout")) as send:
            with self.assertRaises(TransportError):
                adapter.send_controller(dict(self.payload, model="synthetic-model"), selections=[])
        send.assert_called_once()
        events = self.verified_trace(adapter)
        self.assertEqual([event["event"] for event in events], ["egress_decision", "send_attempt", "send_result"])
        self.assertEqual(events[-1]["delivery"], "delivery_unknown")
        self.assertIsNone(events[-1]["status"])
        self.assertIsNone(events[-1]["response"])

    def test_audit_failure_prevents_transport(self):
        controller = ScriptedTransport([{"scripted": True}])
        adapter = self.adapter(controller)
        record = adapter._record

        def fail_before_send(event, **fields):
            if event == "send_attempt":
                raise OSError("trace unavailable")
            record(event, **fields)

        with patch.object(adapter, "_record", side_effect=fail_before_send):
            with self.assertRaises(OSError):
                adapter.send_controller(self.payload, selections=[])
        self.assertEqual(controller.requests, [])
        self.assertEqual([event["event"] for event in self.verified_trace(adapter)], ["egress_decision"])

    def test_http_error_preserves_original_response_without_retry(self):
        self.bundle["run"]["controller"].update(mode="hosted", model="synthetic-model")
        controller = HttpTransport("https://provider.example.invalid/v1/chat/completions")
        adapter = self.adapter(controller)
        response = TransportResponse(status=503, body=b"upstream unavailable\xff")
        with patch.object(controller, "send", return_value=response) as send:
            result = adapter.send_controller(dict(self.payload, model="synthetic-model"), selections=[])
        send.assert_called_once()
        self.assertEqual(result, response)
        event = self.verified_trace(adapter)[-1]
        self.assertEqual(event["delivery"], "http_response_observed")
        self.assertEqual(event["status"], 503)
        self.assertEqual(event["error_type"], "http_status")
        self.assertEqual(recorded_bytes(event["response"]), response.body)

    def test_usage_parser_failure_keeps_received_response_bytes(self):
        self.bundle["run"]["controller"].update(mode="hosted", model="synthetic-model")
        controller = HttpTransport("https://provider.example.invalid/v1/chat/completions")
        adapter = self.adapter(controller)
        response = TransportResponse(status=200, body=b"[" * 20000 + b"0" + b"]" * 20000)
        with patch.object(controller, "send", return_value=response):
            self.assertEqual(adapter.send_controller(dict(self.payload, model="synthetic-model"),
                                                     selections=[]), response)
        event = self.verified_trace(adapter)[-1]
        self.assertEqual(event["event"], "send_result")
        self.assertEqual(recorded_bytes(event["response"]), response.body)
        self.assertIsNone(event["usage"]["input_tokens"])

    def test_bad_proposals_and_fields_do_not_send(self):
        controller = ScriptedTransport([{"scripted": True}])
        adapter = self.adapter(controller)
        args = self.cloud_proposal["arguments"]
        with self.assertRaises(ContractError):
            adapter.record_proposal("forged", dict(self.cloud_proposal, arguments=dict(args, scope={})))
        adapter.record_proposal("call_cloud", dict(self.cloud_proposal, arguments=dict(args, fields=["missing"])))
        with self.assertRaisesRegex(RegistryError, "unknown_field"):
            adapter.release_to_cloud("call_cloud")
        with self.assertRaisesRegex(RegistryError, "unknown_field"):
            adapter.send_controller(self.payload, selections=[{"handle": "calendar.raw", "fields": ["missing"]}])
        self.assertEqual(controller.requests, [])
        self.assertEqual([event["event"] for event in self.verified_trace(adapter)], ["tool_proposal"])

    def test_duplicate_release_cannot_send_again(self):
        adapter = self.adapter(ScriptedTransport([]))
        adapter.record_proposal("call_cloud", self.cloud_proposal)
        adapter.release_to_cloud("call_cloud")
        with self.assertRaisesRegex(ValueError, "already been handled"):
            adapter.release_to_cloud("call_cloud")
        with self.assertRaises(FileExistsError):
            self.adapter(ScriptedTransport([]))
        self.assertEqual(sum(event["event"] == "receiver_record" for event in self.verified_trace(adapter)), 1)

    def test_scripted_response_is_separate_from_receiver_evidence(self):
        controller = ScriptedTransport([{"scripted": True}])
        adapter = self.adapter(controller)
        adapter.send_controller(self.payload, selections=[])
        events = self.verified_trace(adapter)
        self.assertEqual(events[-1]["delivery"], "scripted_response_observed")
        self.assertEqual(recorded_bytes(events[1]["body"]), controller.requests[0])
        self.assertEqual(json.loads(recorded_bytes(events[-1]["response"])), {"scripted": True})
        self.assertNotIn("receiver_record", [event["event"] for event in events])


if __name__ == "__main__":
    unittest.main()
