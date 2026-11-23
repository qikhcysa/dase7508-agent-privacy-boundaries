"""Verify the bounded v1 loop with scripts and real loopback HTTP, never paid models."""

import base64
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from agent_privacy.hosted import ROOT, run_agent
from agent_privacy.hosted_config import HostedConfig
from contracts.validate import load_json, validate
from member_a.agent_core.transport import HttpTransport, TransportError, TransportResponse


def call(call_id, name, arguments):
    return {"id": call_id, "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments)}}


def reply(message, finish="tool_calls"):
    return {"model": "glm-5.3-flash", "choices": [{"finish_reason": finish, "message": message}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


class SyntheticModel:
    mode = "scripted"
    endpoint = "scripted://hosted-loop-test"

    def __init__(self, override=None):
        self.requests = []
        self.override = override

    def send(self, body):
        payload = json.loads(body)
        self.requests.append(payload)
        if self.override:
            value = self.override(payload, len(self.requests))
            if value is not None:
                return TransportResponse(200, json.dumps(value).encode())
        step = len(self.requests)
        if step == 1:
            catalog = json.loads(payload["messages"][1]["content"].split("Asset catalog: ")[1])
            value = reply({"role": "assistant", "content": None, "reasoning_content": "original reasoning",
                           "tool_calls": [call("read_document", "release", {
                               "handle": catalog[0]["handle"], "fields": ["text"],
                               "recipient": "controller"})]})
            value["choices"][0]["message"]["tool_calls"][0]["index"] = 0
        elif step == 2:
            value = reply({"role": "assistant", "content": None,
                           "tool_calls": [call("local_schedule", "schedule", {"mode": "primary"})]})
        else:
            tool_result = json.loads(payload["messages"][-1]["content"])
            if tool_result.get("reason") == "primary_timeout":
                value = reply({"role": "assistant", "content": None,
                               "tool_calls": [call("recovery_schedule", "schedule",
                                                   {"mode": "recovery"})]})
            else:
                slots = tool_result["slots"]
                value = reply({"role": "assistant", "content": json.dumps({
                    "agenda": ["Confirm the prototype boundary", "Assign T01 implementation and review",
                               "Agree on a pilot verification command"], "slots": slots})}, "stop")
        return TransportResponse(200, json.dumps(value).encode())


class HostedTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        self.config = HostedConfig(api_key="synthetic_header_only_secret")

    def run_attempt(self, model=None, config=None, name="attempt", fault="F0"):
        directory = self.directory / name
        result = run_agent(config or self.config, output_dir=directory,
                           transport=model if model is not None else SyntheticModel(), fault=fault)
        bundle = load_json(directory / "bundle.json")
        validate("bundle", bundle)
        self.assertTrue(result["bundle_valid"])
        return result, bundle

    def test_complete_loop_preserves_reasoning_manifest_and_usage(self):
        model = SyntheticModel()
        result, bundle = self.run_attempt(model)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["tool_calls"], 2)
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["usage"], {"input_tokens": 30, "output_tokens": 15, "cost_usd": None})
        self.assertEqual(result["controller_mode"], "scripted")
        self.assertIsNone(bundle["run"]["controller"]["model"])
        self.assertEqual(model.requests[1]["messages"][3]["reasoning_content"], "original reasoning")
        self.assertEqual(model.requests[0]["thinking"], {"type": "enabled", "clear_thinking": False})
        self.assertEqual(model.requests[0]["tool_choice"], "auto")
        sends = [event for event in bundle["trace"] if event["event"] == "send_attempt"]
        self.assertEqual(len(sends), 3)
        for event in sends:
            data = base64.b64decode(event["body"]["base64"])
            self.assertNotIn(b"SYNTHETIC-PRIVATE-CALENDAR-CANARY", data)
            self.assertNotIn(b"SYNTHETIC-PRIVATE-PHONE", data)
            self.assertNotIn(self.config.api_key.encode(), data)
        doc = next(obj for obj in bundle["objects"] if obj["meta"]["source"] == "meeting_document")
        self.assertIn({"handle": doc["handle"], "fields": ["text"]}, sends[1]["selections"])
        self.assertIn({"handle": doc["handle"], "fields": ["text"]}, sends[2]["selections"])
        self.assertEqual(bundle["trace"][-1]["event"], "run_finished")
        for path in (self.directory / "attempt").glob("*.json*"):
            self.assertNotIn(self.config.api_key, path.read_text(encoding="utf-8"))

    def test_formal_attacked_s1_s2_records_protocol_identity(self):
        protocol = "a" * 64
        for policy in ("S1", "S2"):
            with self.subTest(policy=policy):
                directory = self.directory / ("formal_" + policy)
                result = run_agent(
                    self.config, output_dir=directory, transport=SyntheticModel(),
                    document_variant="attacked", policy=policy, phase="formal",
                    protocol_sha256=protocol,
                )
                bundle = load_json(directory / "bundle.json")
                validate("bundle", bundle)
                self.assertEqual(bundle["run"]["phase"], "formal")
                self.assertEqual(bundle["run"]["protocol_sha256"], protocol)
                manifest = load_json(directory / "manifest.json")
                self.assertEqual(manifest["phase"], "formal")
                self.assertEqual(manifest["protocol_sha256"], protocol)
                self.assertEqual(result["status"], "completed")

        with self.assertRaisesRegex(ValueError, "formal_protocol_sha256_required"):
            run_agent(self.config, output_dir=self.directory / "missing_protocol",
                      transport=SyntheticModel(), phase="formal")

    def test_f1_timeout_uses_common_recovery_and_preserves_completion(self):
        model = SyntheticModel()
        result, bundle = self.run_attempt(model, name="f1", fault="F1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["tool_calls"], 3)
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(bundle["run"]["fault"], "F1")
        proposals = [event["proposal"] for event in bundle["trace"]
                     if event["event"] == "tool_proposal"]
        self.assertEqual([proposal["arguments"].get("mode") for proposal in proposals
                          if proposal["name"] == "schedule"], ["primary", "recovery"])
        tools = [json.loads(message["content"]) for message in
                 load_json(self.directory / "f1" / "conversation.json")
                 if message["role"] == "tool"]
        self.assertIn({"status": "blocked_or_failed", "reason": "primary_timeout"}, tools)
        producers = [obj["meta"]["producer"] for obj in bundle["objects"]
                     if obj["meta"]["source"] == "local_tool"]
        self.assertEqual(producers, ["minimal_scheduler"])
        self.assertEqual(len(model.requests), 4)

    def test_f0_and_f1_share_setup_except_declared_fault(self):
        f0_model, f1_model = SyntheticModel(), SyntheticModel()
        _f0_result, f0 = self.run_attempt(f0_model, name="paired_f0", fault="F0")
        _f1_result, f1 = self.run_attempt(f1_model, name="paired_f1", fault="F1")
        for run in (f0["run"], f1["run"]):
            run.pop("attempt_id")
            run.pop("scope")
        f0_fault, f1_fault = f0["run"].pop("fault"), f1["run"].pop("fault")
        self.assertEqual((f0_fault, f1_fault), ("F0", "F1"))
        self.assertEqual(f0["run"], f1["run"])
        self.assertEqual(f0["fixture"], f1["fixture"])
        f0_instructions = f0_model.requests[0]["messages"][1]["content"].split("\nAsset catalog: ")[0]
        f1_instructions = f1_model.requests[0]["messages"][1]["content"].split("\nAsset catalog: ")[0]
        self.assertEqual(f0_instructions, f1_instructions)

    def test_fault_is_trusted_runtime_configuration_only(self):
        directory = self.directory / "invalid_fault"
        with self.assertRaisesRegex(ValueError, "fault must be F0 or F1"):
            run_agent(self.config, output_dir=directory, transport=SyntheticModel(), fault="F2")
        self.assertFalse(directory.exists())

    def test_f0_and_f1_offloads_use_the_common_egress_adapter(self):
        for fault in ("F0", "F1"):
            with self.subTest(fault=fault):
                state = {}

                def offload(payload, _step):
                    latest = payload["messages"][-1]
                    if latest["role"] != "tool":
                        return None
                    tool_result = json.loads(latest["content"])
                    if tool_result.get("reason") == "primary_timeout":
                        return reply({"role": "assistant", "content": None, "tool_calls": [
                            call("recovery_schedule", "schedule", {"mode": "recovery"})]})
                    if "slots" in tool_result and "slots" not in state:
                        state["slots"] = tool_result["slots"]
                        return reply({"role": "assistant", "content": None, "tool_calls": [
                            call("release_slots", "release", {
                                "handle": tool_result["handle"], "fields": ["slots"],
                                "recipient": "mock_cloud"})]})
                    if tool_result.get("status") == "mock_response_observed":
                        return reply({"role": "assistant", "content": json.dumps({
                            "agenda": ["Use the lawful local schedule"],
                            "slots": state["slots"]})}, "stop")
                    return None

                result, bundle = self.run_attempt(SyntheticModel(offload),
                                                  name="offload_" + fault, fault=fault)
                self.assertEqual(result["status"], "completed")
                sends = [event for event in bundle["trace"]
                         if event["event"] == "send_attempt" and event["channel"] == "release"]
                self.assertEqual(len(sends), 1)
                self.assertEqual(sends[0]["recipient"], "mock_cloud")
                self.assertTrue(any(event["event"] == "release_request"
                                    for event in bundle["trace"]))
                self.assertTrue(any(event["event"] == "receiver_record"
                                    and event["send_id"] == sends[0]["send_id"]
                                    for event in bundle["trace"]))

    def test_loopback_http_uses_bearer_header_and_records_exact_bytes(self):
        model, observed = SyntheticModel(), []

        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                observed.append((body, self.headers.get("Authorization")))
                response = model.send(body)
                self.send_response(response.status)
                self.send_header("Content-Length", str(len(response.body)))
                self.end_headers()
                self.wfile.write(response.body)

            def log_message(self, *_args):
                pass

        with HTTPServer(("127.0.0.1", 0), Receiver) as server:
            thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            thread.start()
            try:
                endpoint = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
                transport = HttpTransport(endpoint, api_key=self.config.api_key, timeout=3)
                result, bundle = self.run_attempt(transport)
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["controller_mode"], "hosted")
        events = [e for e in bundle["trace"] if e["event"] == "send_attempt"]
        self.assertEqual(len(observed), 3)
        for (body, authorization), event in zip(observed, events):
            self.assertEqual(authorization, "Bearer " + self.config.api_key)
            self.assertEqual(body, base64.b64decode(event["body"]["base64"]))
        self.assertTrue(all(e["delivery"] == "http_response_observed"
                            for e in bundle["trace"] if e["event"] == "send_result"))

    def test_full_batch_checked_before_any_tool_effect(self):
        def bad_batch(_payload, step):
            if step == 1:
                return reply({"role": "assistant", "tool_calls": [
                    call("one", "schedule", {"mode": "primary"}),
                    call("two", "release", {"handle": "obj_nope", "fields": [], "recipient": "controller"})]})
        result, bundle = self.run_attempt(SyntheticModel(bad_batch))
        self.assertEqual(result["error_type"], "contract_error")
        self.assertEqual(result["tool_calls"], 0)
        self.assertFalse(any(e["event"] == "tool_proposal" for e in bundle["trace"]))
        self.assertFalse(any(o["meta"]["source"] == "local_tool" for o in bundle["objects"]))

    def test_recovery_rejects_whole_batch_without_scheduling_effects(self):
        for modes in (["recovery"], ["primary", "recovery"], ["recovery", "primary"]):
            with self.subTest(modes=modes):
                calls = [call(f"schedule_{i}", "schedule", {"mode": mode})
                         for i, mode in enumerate(modes)]
                model = SyntheticModel(lambda _p, _n: reply({"role": "assistant", "tool_calls": calls}))
                result, bundle = self.run_attempt(model, name="_".join(modes))
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["error_type"], "recovery_without_primary_timeout")
                self.assertEqual(result["tool_calls"], 0)
                self.assertEqual(len(model.requests), 1)
                self.assertFalse(any(e["event"] == "tool_proposal" for e in bundle["trace"]))
                self.assertFalse(any(o["meta"]["source"] == "local_tool" for o in bundle["objects"]))

    def test_f1_recovery_requires_timeout_in_an_earlier_batch(self):
        for modes in (["recovery"], ["primary", "recovery"], ["recovery", "primary"]):
            with self.subTest(modes=modes):
                calls = [call(f"schedule_{i}", "schedule", {"mode": mode})
                         for i, mode in enumerate(modes)]
                model = SyntheticModel(lambda _p, _n: reply({"role": "assistant", "tool_calls": calls}))
                result, bundle = self.run_attempt(model, name="f1_" + "_".join(modes), fault="F1")
                self.assertEqual(result["error_type"], "recovery_without_primary_timeout")
                self.assertEqual(result["tool_calls"], 0)
                self.assertFalse(any(e["event"] == "tool_proposal" for e in bundle["trace"]))

    def test_rejects_duplicate_calls_unknown_handles_and_forged_authority(self):
        cases = {
            "duplicate": ([call("same", "schedule", {"mode": "primary"})] * 2, "duplicate_call_id"),
            "unknown": ([call("unknown", "release", {"handle": "obj_unknown", "fields": ["text"],
                                                      "recipient": "controller"})], "unknown_handle"),
            "authority": ([call("forged", "schedule", {"mode": "primary", "scope": {}})], "contract_error"),
            "fault": ([call("fault", "schedule", {"mode": "primary", "fault": "F0"})], "contract_error"),
            "memory": ([call("memory", "save_memory", {"content": "untrusted"})], "unsupported_tool"),
        }
        for name, (calls, expected) in cases.items():
            with self.subTest(name=name):
                model = SyntheticModel(lambda _p, _n: reply({"role": "assistant", "tool_calls": calls}))
                result, _bundle = self.run_attempt(model, name=name)
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["error_type"], expected)
                self.assertEqual(len(model.requests), 1)

    def test_truncated_and_fabricated_final_are_not_completed(self):
        def truncated(_payload, _step):
            return reply({"role": "assistant", "content": "partial"}, "length")
        result, _ = self.run_attempt(SyntheticModel(truncated), name="truncated")
        self.assertEqual(result["error_type"], "incomplete_model_response")

        def fabricated(_payload, step):
            if step == 3:
                return reply({"role": "assistant", "content": json.dumps({"agenda": ["agenda"],
                    "slots": [{"start": "2026-11-02T10:00:00+08:00", "end": "2026-11-02T10:30:00+08:00"}]})}, "stop")
        result, _ = self.run_attempt(SyntheticModel(fabricated), name="fabricated")
        self.assertEqual(result["error_type"], "final_slots_differ_from_local_tool")

    def test_limits_and_fresh_attempts(self):
        result, _ = self.run_attempt(config=HostedConfig(api_key="synthetic_key", max_steps=1), name="limited")
        self.assertEqual((result["status"], result["error_type"]), ("incomplete", "step_limit"))
        first, a = self.run_attempt(name="first")
        second, b = self.run_attempt(name="second")
        self.assertNotEqual(a["run"]["scope"], b["run"]["scope"])
        self.assertFalse({o["handle"] for o in a["objects"]} & {o["handle"] for o in b["objects"]})
        with self.assertRaises(FileExistsError):
            self.run_attempt(name="first")

    def test_http_error_and_unknown_delivery_are_preserved_without_retries(self):
        class Failure:
            mode = "http"
            endpoint = "https://provider.example.invalid/chat/completions"
            count = 0
            unknown = False

            def send(self, body):
                self.count += 1
                if self.unknown:
                    raise TransportError("timeout")
                return TransportResponse(429, b'{"error":"insufficient quota"}')

        for unknown in (False, True):
            with self.subTest(unknown=unknown):
                model = Failure()
                model.unknown = unknown
                result, bundle = self.run_attempt(model, name=str(unknown))
                self.assertEqual(model.count, 1)
                self.assertEqual(result["error_type"], "transport_error" if unknown else "http_status_429")
                event = next(e for e in bundle["trace"] if e["event"] == "send_result")
                self.assertEqual(event["delivery"], "delivery_unknown" if unknown else "http_response_observed")
                self.assertIsNone(result["usage"]["input_tokens"])


if __name__ == "__main__":
    unittest.main()
