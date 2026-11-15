"""H1 continuation acceptance: immutable context and isolated ordinary attempts."""

import base64
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from agent_privacy.hosted import ROOT, run_agent
from agent_privacy.hosted_config import HostedConfig
from contracts.validate import load_json, validate
from member_a.agent_core.transport import HttpTransport, TransportResponse


SUMMARY = "Confirm prototype boundary; assign implementation and review; agree pilot verification."


class SummaryModel:
    mode = "scripted"
    endpoint = "scripted://h1-summary-test"

    def __init__(self):
        self.requests = []

    def send(self, body):
        self.requests.append(json.loads(body))
        return TransportResponse(200, json.dumps({"choices": [{"finish_reason": "stop",
            "message": {"role": "assistant", "content": SUMMARY}}],
            "usage": {"prompt_tokens": 13, "completion_tokens": 7}}).encode())


def _call(identifier, name, arguments):
    return {"id": identifier, "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments)}}


class MobileModel:
    mode = "scripted"
    endpoint = "scripted://h1-mobile-test"

    def __init__(self, foreign_handle=None, fail=False):
        self.requests = []
        self.foreign_handle = foreign_handle
        self.fail = fail

    def send(self, body):
        payload = json.loads(body)
        self.requests.append(payload)
        step = len(self.requests)
        if step == 1:
            catalog_message = next(message for message in payload["messages"]
                                   if "Asset catalog: " in (message.get("content") or ""))
            catalog = json.loads(catalog_message["content"].split("Asset catalog: ")[1])
            handle = self.foreign_handle or catalog[0]["handle"]
            message = {"role": "assistant", "content": None, "tool_calls": [
                _call("load_context", "release", {"handle": handle, "fields": ["text"],
                                                    "recipient": "controller"})]}
        elif step == 2:
            message = {"role": "assistant", "content": None, "tool_calls": [
                _call("schedule_slots", "schedule", {"mode": "primary"})]}
        else:
            tool_result = json.loads(payload["messages"][-1]["content"])
            if tool_result.get("reason") == "primary_timeout":
                message = {"role": "assistant", "content": None, "tool_calls": [
                    _call("recovery_slots", "schedule", {"mode": "recovery"})]}
            else:
                message = {"role": "assistant", "content": json.dumps({
                    "agenda": [SUMMARY], "slots": tool_result["slots"]})}
        return TransportResponse(200, json.dumps({"choices": [{
            "finish_reason": "length" if self.fail else ("tool_calls" if "tool_calls" in message else "stop"),
            "message": message}]}).encode())


class HostedH1Tests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.directory = Path(self.folder.name)
        self.config = HostedConfig(api_key="synthetic_h1_header_only_key")

    def prepare(self, **kwargs):
        from agent_privacy.handoff import prepare_handoff
        self.summary_model = SummaryModel()
        return prepare_handoff(self.config, cache_dir=self.directory / "cache",
                               transport=self.summary_model, **kwargs)

    def attempt(self, artifact, name="mobile", model=None, **kwargs):
        directory = self.directory / name
        model = model or MobileModel()
        result = run_agent(self.config, handoff_path=artifact, output_dir=directory,
                           transport=model, **kwargs)
        bundle = load_json(directory / "bundle.json")
        validate("bundle", bundle)
        self.assertTrue(result["bundle_valid"])
        return result, bundle, model

    def test_mobile_load_retains_desktop_provenance_and_logs_exact_summary(self):
        artifact = self.prepare()
        original_bytes = artifact.read_bytes()
        result, bundle, model = self.attempt(artifact)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(bundle["run"]["handoff"], "H1")
        self.assertEqual(bundle["run"]["scope"]["device_id"], "mobile")
        summary = next(obj for obj in bundle["objects"] if obj["meta"]["source"] == "model_summary")
        source = next(obj for obj in bundle["objects"] if obj["meta"]["source"] == "meeting_document")
        self.assertEqual(summary["value"], {"text": SUMMARY})
        self.assertEqual(summary["meta"]["message_role"], "assistant")
        self.assertEqual(summary["meta"]["integrity"], "untrusted")
        self.assertEqual(summary["meta"]["derivation"], [source["handle"]])
        self.assertEqual(source["meta"]["message_role"], "tool")
        self.assertEqual(summary["meta"]["original_scope"], source["meta"]["original_scope"])
        self.assertEqual(source["meta"]["original_scope"]["device_id"], "desktop")
        self.assertEqual(source["meta"]["original_scope"]["task_id"], bundle["run"]["scope"]["task_id"])
        self.assertNotEqual(source["meta"]["original_scope"]["trial_id"], bundle["run"]["scope"]["trial_id"])
        loaded = next(event for event in bundle["trace"] if event["event"] == "context_loaded")
        self.assertEqual(loaded["handle"], summary["handle"])
        self.assertEqual(loaded["loaded_message_role"], "tool")
        self.assertEqual(loaded["source_metadata"], summary["meta"])
        prior = bundle["trace"][:bundle["trace"].index(loaded)]
        self.assertTrue(any(event["event"] == "policy_decision" and event["operation"] == "load"
                            and event["reference_id"] == summary["handle"] and event["allowed"]
                            for event in prior))
        envelopes = [json.loads(message["content"]) for message in model.requests[1]["messages"]
                     if message["role"] == "tool"]
        self.assertEqual(envelopes[0]["value"], {"text": SUMMARY})
        self.assertEqual(envelopes[0]["source_metadata"], summary["meta"])
        self.assertEqual(artifact.read_bytes(), original_bytes)
        for event in bundle["trace"]:
            if event["event"] == "send_attempt":
                sent = base64.b64decode(event["body"]["base64"])
                self.assertNotIn(b"SYNTHETIC-PRIVATE-CALENDAR-CANARY", sent)
                self.assertNotIn(b"SYNTHETIC-PRIVATE-PHONE", sent)
                self.assertNotIn(self.config.api_key.encode(), sent)

    def test_one_summary_reused_across_faults_with_fresh_mutable_state(self):
        from agent_privacy.handoff import prepare_handoff
        artifact = self.prepare()
        before = hashlib.sha256(artifact.read_bytes()).hexdigest()
        first_result, first, _ = self.attempt(artifact, "first", fault="F0")
        again = prepare_handoff(self.config, cache_dir=self.directory / "cache", transport=self.summary_model)
        second_result, second, second_model = self.attempt(again, "second", fault="F1")
        self.assertEqual(first_result["status"], "completed")
        self.assertEqual(second_result["status"], "completed")
        self.assertEqual((first["run"]["fault"], second["run"]["fault"]), ("F0", "F1"))
        self.assertEqual((first_result["tool_calls"], second_result["tool_calls"]), (2, 3))
        self.assertEqual(artifact, again)
        self.assertEqual(len(self.summary_model.requests), 1)
        self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), before)
        self.assertEqual(first["handoff"], second["handoff"])
        first_summary = next(obj for obj in first["objects"] if obj["meta"]["source"] == "model_summary")
        second_summary = next(obj for obj in second["objects"] if obj["meta"]["source"] == "model_summary")
        self.assertEqual(first_summary, second_summary)
        self.assertNotEqual(first["run"]["scope"]["trial_id"], second["run"]["scope"]["trial_id"])
        self.assertNotEqual(first["run"]["scope"]["session_id"], second["run"]["scope"]["session_id"])
        first_local = {obj["handle"] for obj in first["objects"] if obj["meta"]["source"] == "local_tool"}
        second_local = {obj["handle"] for obj in second["objects"] if obj["meta"]["source"] == "local_tool"}
        self.assertFalse(first_local & second_local)
        self.assertEqual(len(second_model.requests[0]["messages"]), 3)
        for name in ("first", "second"):
            reset = load_json(self.directory / name / "reset.json")
            self.assertEqual(reset["bindings_after"], 0)
            self.assertTrue(reset["conversation_cleared"])
            self.assertTrue(reset["audit_preserved"])
            self.assertTrue((self.directory / name / "events.jsonl").is_file())

    def test_previous_attempt_derived_handle_cannot_be_read(self):
        artifact = self.prepare()
        _result, first, _ = self.attempt(artifact, "first")
        old_handle = next(obj["handle"] for obj in first["objects"] if obj["meta"]["source"] == "local_tool")
        result, bundle, model = self.attempt(artifact, "foreign", model=MobileModel(foreign_handle=old_handle))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "unknown_handle")
        self.assertEqual(len(model.requests), 1)
        self.assertFalse(any(event["event"] == "context_loaded" for event in bundle["trace"]))
        self.assertTrue((self.directory / "foreign" / "reset.json").exists())

    def test_numeric_substrings_in_opaque_summary_handle_remain_usable(self):
        identifiers = [SimpleNamespace(hex=value) for value in (
            "a" * 32, "b" * 32, "aaaaaaaa12345678" + "b" * 16)]
        with patch("agent_privacy.scoped_registry.uuid4", side_effect=identifiers):
            artifact = self.prepare()
        result, bundle, model = self.attempt(artifact)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(bundle["run"]["policy"], "S0")
        self.assertIn("12345678", bundle["handoff"]["summary_handle"])
        self.assertIn(bundle["handoff"]["summary_handle"], model.requests[0]["messages"][1]["content"])

    def test_prior_attempt_timeout_does_not_authorize_fresh_recovery(self):
        artifact = self.prepare()
        first, _bundle, _model = self.attempt(artifact, "completed_f1", fault="F1")
        self.assertEqual(first["status"], "completed")

        class PrematureRecovery(MobileModel):
            def send(self, body):
                self.requests.append(json.loads(body))
                return TransportResponse(200, json.dumps({"choices": [{"finish_reason": "tool_calls",
                    "message": {"role": "assistant", "content": None, "tool_calls": [
                        _call("recovery", "schedule", {"mode": "recovery"})]}}]}).encode())

        result, bundle, _model = self.attempt(artifact, "fresh_f1", fault="F1", model=PrematureRecovery())
        self.assertEqual(result["error_type"], "recovery_without_primary_timeout")
        self.assertEqual(result["tool_calls"], 0)
        self.assertFalse(any(event["event"] == "tool_proposal" for event in bundle["trace"]))
        self.assertEqual(result["reset"]["bindings_after"], 0)

    def test_rejected_foreign_task_load_is_logged_without_model_send(self):
        from agent_privacy.handoff import HandoffError
        artifact = self.prepare()
        model = MobileModel()
        directory = self.directory / "denied"
        with self.assertRaises(HandoffError):
            run_agent(self.config, handoff_path=artifact, output_dir=directory,
                      transport=model, task_id="foreign_task")
        self.assertFalse(model.requests)
        load = load_json(directory / "handoff-load.json")
        self.assertFalse(load["allowed"])
        self.assertFalse(load["summary_loaded"])
        self.assertEqual(load_json(directory / "reset.json")["bindings_after"], 0)
        self.assertFalse((directory / "events.jsonl").exists())

    def test_same_frozen_summary_at_each_existing_policy_and_fault_boundary(self):
        from agent_privacy.egress import EgressAdapter
        from agent_privacy.scoped_registry import ScopedRegistry
        from agent_privacy.static_allowlist import StaticAllowlist

        artifact = self.prepare()
        _result, original, _model = self.attempt(artifact)
        summary = next(obj for obj in original["objects"] if obj["meta"]["source"] == "model_summary")
        artifact_bytes = artifact.read_bytes()
        for policy in ("S0", "S1", "S2"):
            for fault in ("F0", "F1"):
                with self.subTest(policy=policy, fault=fault), ScopedRegistry() as registry:
                    bundle = deepcopy(original)
                    bundle["run"].update(policy=policy, fault=fault)
                    bundle["trace"] = []
                    for record in bundle["objects"]:
                        registry.put_record(record)
                    registry.bind_context(summary["handle"], bundle["run"]["scope"],
                                          binding_ref=bundle["handoff"]["artifact_id"])
                    trace = self.directory / (policy + "_" + fault + ".jsonl")
                    options = ({"static_allowlist": StaticAllowlist({summary["handle"]: ["text"]})}
                               if policy == "S2" else {})
                    adapter = EgressAdapter(bundle["run"], registry, controller=SummaryModel(),
                                            trace_path=trace, **options)
                    loaded = adapter.record_context_load(summary["handle"])
                    adapter.send_controller({"model": self.config.model, "messages": [{
                        "role": "user", "content": json.dumps({"untrusted_summary": loaded["value"],
                                                                    "source_metadata": loaded["meta"]})}]},
                        selections=[{"handle": summary["handle"], "fields": ["text"]}])
                    adapter.finish(status="incomplete", agenda=[], slots=[], error_type="boundary_probe_only")
                    bundle["trace"] = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
                    validate("bundle", bundle)
                    self.assertEqual(loaded, summary)
                    self.assertEqual(bundle["handoff"], original["handoff"])
                    self.assertEqual(artifact.read_bytes(), artifact_bytes)
        self.assertEqual(len(self.summary_model.requests), 1)

    def test_loopback_http_records_generation_and_mobile_request_bytes(self):
        from agent_privacy.handoff import prepare_handoff

        summary_model, mobile_model, observed = SummaryModel(), MobileModel(), []

        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                observed.append((body, self.headers.get("Authorization")))
                response = (mobile_model if "tools" in json.loads(body) else summary_model).send(body)
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
                config = HostedConfig(api_key="synthetic_http_header_only", base_url=endpoint, timeout=3)
                artifact = prepare_handoff(config, cache_dir=self.directory / "http-cache",
                    transport=HttpTransport(endpoint, api_key=config.api_key, timeout=3))
                directory = self.directory / "http-mobile"
                result = run_agent(config, handoff_path=artifact, output_dir=directory,
                    transport=HttpTransport(endpoint, api_key=config.api_key, timeout=3))
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(summary_model.requests), 1)
        generation = load_json(artifact.parent / "generation-bundle.json")
        mobile = load_json(directory / "bundle.json")
        self.assertEqual(mobile["handoff"]["generation"]["controller_mode"], "hosted")
        events = generation["trace"] + mobile["trace"]
        sends = [event for event in events if event["event"] == "send_attempt"]
        self.assertEqual(len(observed), 4)
        for (body, authorization), event in zip(observed, sends):
            self.assertEqual(authorization, "Bearer " + config.api_key)
            self.assertEqual(body, base64.b64decode(event["body"]["base64"]))
            self.assertNotIn(config.api_key.encode(), body)
        for bundle in (generation, mobile):
            validate("bundle", bundle)

    def test_continuation_in_a_separate_process(self):
        artifact = self.prepare()
        directory = self.directory / "subprocess"
        program = (
            "import sys; sys.path.insert(0, 'tests'); "
            "from test_hosted_h1 import MobileModel; "
            "from agent_privacy.hosted import run_agent; "
            "from agent_privacy.hosted_config import HostedConfig; "
            "r=run_agent(HostedConfig(api_key='synthetic'), handoff_path=sys.argv[1], "
            "output_dir=sys.argv[2], transport=MobileModel(), fault='F1'); "
            "raise SystemExit(0 if r['status']=='completed' and r['bundle_valid'] else 1)"
        )
        completed = subprocess.run([sys.executable, "-c", program, str(artifact), str(directory)],
                                   cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        bundle = load_json(directory / "bundle.json")
        validate("bundle", bundle)
        self.assertEqual(bundle["run"]["scope"]["device_id"], "mobile")
        self.assertEqual(bundle["trace"][-1]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
