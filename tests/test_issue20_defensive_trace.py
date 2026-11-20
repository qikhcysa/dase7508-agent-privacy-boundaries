"""Offline defensive trace smoke tests against the frozen v1 contract.

No model, tool, runner, transport, or outbound network is invoked.
"""
import unittest

from agent_privacy.redaction import PHONE_REPLACEMENT, redact_value
from contracts.validate import ContractError, validate


def synthetic(event, **fields):
    return {
        "event": event,
        "event_id": "synthetic-event",
        "timestamp": "2026-01-01T00:00:00Z",
        "attempt_id": "synthetic-attempt",
        "scope": {
            "user_id": "synthetic-user",
            "task_id": "synthetic-task",
            "session_id": "synthetic-session",
            "trial_id": "synthetic-trial",
            "device_id": "synthetic-device",
        },
        **fields,
    }


class DefensiveTraceTests(unittest.TestCase):
    def test_benign_completion(self):
        validate("trace_event", synthetic(
            "run_finished", status="completed", agenda=["Discuss the demo schedule"],
            slots=[{"start": "2026-01-01T01:00:00Z", "end": "2026-01-01T01:30:00Z"}],
            error_type=None,
        ))

    def test_mock_policy_refusal(self):
        validate("trace_event", synthetic(
            "policy_decision", operation="release", reference_id="synthetic-selection",
            allowed=False, reason="scope_denied",
        ))

    def test_mock_transport_timeout(self):
        validate("trace_event", synthetic(
            "send_result", send_id="synthetic-send", transport_mode="in_process_mock",
            delivery="delivery_unknown", status=None, response=None, error_type="TimeoutError",
            latency_ms=0, usage={"input_tokens": None, "output_tokens": None, "cost_usd": None},
        ))

    def test_mock_tool_failure(self):
        validate("trace_event", synthetic(
            "run_finished", status="error", agenda=[], slots=[], error_type="MockToolError",
        ))

    def test_missing_scope_fails(self):
        event = synthetic(
            "policy_decision", operation="release", reference_id="synthetic-selection",
            allowed=False, reason="scope_denied",
        )
        del event["scope"]
        with self.assertRaises(ContractError):
            validate("trace_event", event)

    def test_completed_run_cannot_have_empty_slots(self):
        with self.assertRaises(ContractError):
            validate("trace_event", synthetic(
                "run_finished", status="completed", agenda=["Demo"], slots=[], error_type=None,
            ))

    def test_redaction_retains_unrelated_data_and_does_not_mutate_input(self):
        original = {"label": "sample", "nested": ["fake 00000000", 5]}
        result = redact_value(original)
        self.assertEqual(result, {"label": "sample", "nested": ["fake " + PHONE_REPLACEMENT, 5]})
        self.assertEqual(original["nested"], ["fake 00000000", 5])


if __name__ == "__main__":
    unittest.main()
