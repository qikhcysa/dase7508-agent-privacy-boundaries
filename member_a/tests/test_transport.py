"""All HTTP tests use an ephemeral loopback server; no paid API calls."""

import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from agent_core.transport import (
    AuditLog,
    AuditedSender,
    HttpTransport,
    InProcessReceiver,
    ResponseError,
    ScriptedTransport,
    TransportError,
)


@contextmanager
def local_server(status=200, response=b'{"accepted":true}', headers=None):
    receipts = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            receipts.append({"body": body, "path": self.path, "headers": dict(self.headers)})
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/controller", receipts
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "nested" / "audit.jsonl"
        self.audit = AuditLog(self.path)

    def records(self):
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def send(self, transport, payload=None):
        return AuditedSender(transport, self.audit).send(
            {"text": "夏张宁", "z": 1} if payload is None else payload,
            scope={"run_id": "local-test", "step": 1},
            channel="controller",
            configuration="test",
        )

    def test_http_exact_bytes_headers_and_usage(self):
        response = b'{"accepted":true,"usage":{"total_tokens":7}}'
        with local_server(response=response) as (endpoint, receipts):
            result = self.send(HttpTransport(endpoint, api_key="secret-test-key"))
        self.assertTrue(result["accepted"])
        expected = '{"text":"夏张宁","z":1}'.encode("utf-8")
        self.assertEqual(receipts[0]["body"], expected)
        self.assertEqual(receipts[0]["headers"]["Authorization"], "Bearer secret-test-key")
        self.assertEqual(receipts[0]["headers"]["Content-Type"], "application/json")
        attempt, observed = self.records()
        self.assertEqual(attempt["event"], "send_attempt")
        self.assertEqual(attempt["delivery"], "attempted")
        self.assertEqual(base64.b64decode(attempt["body_base64"]), expected)
        self.assertEqual(attempt["body_sha256"], hashlib.sha256(expected).hexdigest())
        self.assertEqual(attempt["body_byte_count"], len(expected))
        self.assertEqual(observed["event"], "http_response")
        self.assertEqual(observed["send_id"], attempt["send_id"])
        self.assertEqual(observed["token_usage"], {"total_tokens": 7})
        self.assertEqual(base64.b64decode(observed["response_base64"]), response)
        self.assertEqual(observed["response_sha256"], hashlib.sha256(response).hexdigest())
        self.assertNotIn("secret-test-key", self.path.read_text(encoding="utf-8"))
        self.assertNotIn("Bearer", self.path.read_text(encoding="utf-8"))

    def test_redirect_is_recorded_and_not_followed(self):
        with local_server(status=307, headers={"Location": "/redirected"}) as (endpoint, receipts):
            with self.assertRaises(ResponseError) as caught:
                self.send(HttpTransport(endpoint))
        self.assertEqual(caught.exception.status, 307)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(self.records()[-1]["status"], 307)

    def test_error_response_preserves_non_json_bytes(self):
        response = b'upstream unavailable\xff'
        with local_server(status=503, response=response) as (endpoint, receipts):
            with self.assertRaises(ResponseError) as caught:
                self.send(HttpTransport(endpoint))
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(len(receipts), 1)
        record = self.records()[-1]
        self.assertEqual(base64.b64decode(record["response_base64"]), response)
        self.assertEqual(record["parse_error"], "UnicodeDecodeError")

    def test_success_status_invalid_json_is_rejected_and_preserved(self):
        for response in (b'not-json', b'[]', b'{"value":NaN}'):
            with self.subTest(response=response):
                with local_server(response=response) as (endpoint, _):
                    with self.assertRaises(ResponseError):
                        self.send(HttpTransport(endpoint))
                self.assertEqual(base64.b64decode(self.records()[-1]["response_base64"]), response)

    def test_scripted_sequence_is_labeled_and_exhaustion_is_not_receipt(self):
        transport = ScriptedTransport([{"step": 1}, {"step": 2}])
        self.assertEqual(self.send(transport), {"step": 1})
        self.assertEqual(self.send(transport), {"step": 2})
        with self.assertRaises(TransportError):
            self.send(transport)
        records = self.records()
        self.assertEqual(records[1]["event"], "scripted_response")
        self.assertEqual(records[1]["transport_mode"], "scripted")
        self.assertEqual(records[-1]["event"], "send_error")
        self.assertEqual(records[-1]["delivery"], "delivery_unknown")
        self.assertEqual(len(transport.requests), 2)
        self.assertFalse(any(r["event"] == "http_response" for r in records))

    def test_mock_receipt_matches_exact_attempt_bytes(self):
        transport = InProcessReceiver()
        result = self.send(transport)
        attempt, received = self.records()
        self.assertEqual(transport.receipts, [base64.b64decode(attempt["body_base64"])])
        self.assertEqual(result["sha256"], attempt["body_sha256"])
        self.assertEqual(received["event"], "mock_receipt")
        self.assertEqual(received["transport_mode"], "in_process_mock")

    def test_attempt_is_flushed_and_provenance_set_before_dispatch(self):
        test = self

        class CheckingReceiver(InProcessReceiver):
            def send(self, body):
                attempt = test.records()[-1]
                test.assertEqual(attempt["event"], "send_attempt")
                test.assertEqual(base64.b64decode(attempt["body_base64"]), body)
                test.assertEqual(sender.last_send_id, attempt["send_id"])
                return super().send(body)

        sender = AuditedSender(CheckingReceiver(), self.audit)
        self.assertIsNone(sender.last_send_id)
        sender.send({}, scope={}, channel="controller", configuration="test")
        first_id = sender.last_send_id
        sender.send({}, scope={}, channel="controller", configuration="test")
        self.assertNotEqual(sender.last_send_id, first_id)
        self.assertEqual(sender.last_send_id, self.records()[-1]["send_id"])

    def test_transport_exception_does_not_log_sensitive_error_text(self):
        class FailingTransport:
            mode = "http"
            endpoint = "https://controller.example.invalid"

            def send(self, body):
                raise OSError("Authorization: Bearer sensitive-key")

        with self.assertRaises(TransportError):
            self.send(FailingTransport())
        self.assertEqual(self.records()[-1]["delivery"], "delivery_unknown")
        self.assertNotIn("sensitive-key", self.path.read_text(encoding="utf-8"))

    def test_endpoint_restrictions(self):
        invalid = (
            "http://example.com/api", "ftp://localhost/api", "https://u:p@example.com/api",
            "https://example.com/api?q=1", "https://example.com/api#part",
            "https://example.com/api?", "https://example.com/api#", "https://example.com:bad",
            " https://example.com", "https://example.com/\npath", "http://localhost.evil/api",
        )
        for endpoint in invalid:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                HttpTransport(endpoint)
        for endpoint in ("http://localhost/api", "http://127.0.0.2/api", "http://[::1]/api", "https://example.com/api"):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(HttpTransport(endpoint).endpoint, endpoint)

    def test_invalid_payload_never_attempts_delivery(self):
        transport = InProcessReceiver()
        with self.assertRaises(ValueError):
            self.send(transport, {"value": float("nan")})
        self.assertEqual(transport.receipts, [])
        self.assertFalse(self.path.exists())

    def test_http_snapshot_has_no_credentials_and_preserves_live_configuration(self):
        with local_server() as (endpoint, receipts):
            transport = HttpTransport(endpoint, api_key="snapshot-secret")
            snapshot = transport.snapshot()
            self.assertEqual(snapshot, {"mode": "http", "endpoint": endpoint})
            self.assertNotIn("snapshot-secret", json.dumps(snapshot))
            transport.restore(json.loads(json.dumps(snapshot)))
            self.send(transport)
            self.assertEqual(receipts[0]["headers"]["Authorization"], "Bearer snapshot-secret")
            for invalid in (None, [], {}, {**snapshot, "endpoint": endpoint + "/other"}, {**snapshot, "mode": "scripted"}):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    transport.restore(invalid)
            self.assertEqual(transport.snapshot(), snapshot)

    def test_scripted_snapshot_restores_cursor_and_requests_without_erasing_audit(self):
        transport = ScriptedTransport([{"step": 1}, {"step": 2}])
        initial = transport.snapshot()
        self.assertEqual(self.send(transport), {"step": 1})
        saved = json.loads(json.dumps(transport.snapshot()))
        saved_requests = transport.requests.copy()
        self.assertEqual(self.send(transport), {"step": 2})
        audit_before_restore = self.path.read_bytes()
        transport.restore(saved)
        self.assertEqual(transport.requests, saved_requests)
        self.assertEqual(transport.snapshot(), saved)
        self.assertEqual(self.path.read_bytes(), audit_before_restore)
        self.assertEqual(self.send(transport), {"step": 2})
        self.assertEqual(len(self.records()), 6)
        transport.restore(initial)
        self.assertEqual(transport.requests, [])
        self.assertEqual(self.send(transport), {"step": 1})
        self.assertEqual(len(self.records()), 8)

    def test_scripted_restore_rejects_incompatible_or_malformed_state_atomically(self):
        transport = ScriptedTransport([{"step": 1}, {"step": 2}])
        transport.send(b"first")
        saved = transport.snapshot()
        invalid_states = [None, [], {}, ScriptedTransport([{"different": True}]).snapshot()]
        invalid_states.extend({**saved, "index": index} for index in (-1, 3, 0.5, True, "1", None))
        invalid_states.extend({**saved, "requests_base64": value} for value in (None, "", [], [2], ["%%%"], ["夏"]))
        invalid_states.append({**saved, "mode": "http"})
        invalid_states.append({**saved, "endpoint": "scripted://other"})
        for invalid in invalid_states:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                transport.restore(invalid)
            self.assertEqual(transport.snapshot(), saved)

    def test_scripted_hash_uses_fixed_script_and_snapshots_are_detached(self):
        responses = [{"step": 1}]
        transport = ScriptedTransport(responses)
        initial = transport.snapshot()
        responses[0]["step"] = 99
        self.assertEqual(transport.snapshot(), initial)
        transport.send(b"\x00\xff")
        saved = transport.snapshot()
        restored = ScriptedTransport([{"step": 1}])
        restored.restore(json.loads(json.dumps(saved)))
        self.assertEqual(restored.requests, [b"\x00\xff"])
        saved["requests_base64"].clear()
        self.assertEqual(transport.requests, [b"\x00\xff"])
        with self.assertRaises(TransportError):
            restored.send(b"exhausted")

    def test_mock_snapshot_restores_exact_receipts_without_erasing_audit(self):
        transport = InProcessReceiver()
        initial = transport.snapshot()
        transport.send(b"\x00\xff")
        saved = json.loads(json.dumps(transport.snapshot()))
        self.send(transport)
        audit_before_restore = self.path.read_bytes()
        transport.restore(saved)
        self.assertEqual(transport.receipts, [b"\x00\xff"])
        self.assertEqual(self.path.read_bytes(), audit_before_restore)
        saved["receipts_base64"].clear()
        self.assertEqual(transport.receipts, [b"\x00\xff"])
        transport.restore(initial)
        self.assertEqual(transport.receipts, [])
        self.assertEqual(len(self.records()), 2)

    def test_mock_restore_rejects_malformed_state_without_mutation(self):
        transport = InProcessReceiver()
        transport.send(b"preserved")
        saved = transport.snapshot()
        invalid_states = [None, [], {}, {**saved, "mode": "http"}, {**saved, "endpoint": "mock://other"}]
        invalid_states.extend({**saved, "receipts_base64": value} for value in (None, "", [2], ["%%%"], ["夏"]))
        for invalid in invalid_states:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                transport.restore(invalid)
            self.assertEqual(transport.snapshot(), saved)

    def test_concurrent_appends_and_reopen_preserve_all_records(self):
        self.audit.append("sentinel", sequence=-1)
        other = AuditLog(self.path)
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit((self.audit if n % 2 else other).append, "parallel", sequence=n)
                for n in range(80)
            ]
            for future in futures:
                future.result()
        records = self.records()
        self.assertEqual(len(records), 81)
        self.assertEqual(records[0]["event"], "sentinel")
        self.assertEqual({r["sequence"] for r in records[1:]}, set(range(80)))
        self.assertEqual(len({r["event_id"] for r in records}), 81)
        self.assertTrue(all(r["timestamp"].endswith("Z") for r in records))


if __name__ == "__main__":
    unittest.main()
