"""Offline scheduling smoke checks through the hosted agent loop."""

import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent_privacy import hosted
from agent_privacy.hosted_config import HostedConfig
from contracts.validate import load_json, validate
from tests.test_hosted import SyntheticModel, reply


class DefensiveSchedulingSmoke(unittest.TestCase):
    def run_attempt(self, model):
        with TemporaryDirectory() as folder:
            output = Path(folder) / "attempt"
            hosted.run_agent(HostedConfig(api_key="synthetic_key"), output_dir=output,
                             transport=model)
            bundle = load_json(output / "bundle.json")
        validate("bundle", bundle)
        self.assertEqual(bundle["trace"][-1]["event"], "run_finished")
        return bundle

    def test_benign_slots_and_log_exclude_private_metadata(self):
        bundle = self.run_attempt(SyntheticModel())
        event = bundle["trace"][-1]
        fixture = bundle["fixture"]
        self.assertEqual(event["status"], "completed")
        self.assertIsNone(event["error_type"])
        self.assertEqual(event["agenda"], fixture["expected_agenda"])
        self.assertEqual(event["slots"], fixture["expected_slots"])

        busy_event = fixture["calendar"]["events"][0]
        contact = fixture["contacts"]["entries"][0]
        private_values = (busy_event["title"], busy_event["location"], contact["phone"])
        controller_bodies = [base64.b64decode(entry["body"]["base64"])
                             for entry in bundle["trace"] if entry["event"] == "send_attempt"]
        self.assertTrue(controller_bodies)
        for value in private_values:
            self.assertNotIn(value, json.dumps(event))
            for body in controller_bodies:
                self.assertNotIn(value.encode(), body)

    def test_refused_provider_never_calls_scheduler(self):
        def refuse(_payload, _step):
            return reply({"role": "assistant", "content": None}, finish="content_filter")

        model = SyntheticModel(refuse)
        with patch.object(hosted, "schedule_fixture", wraps=hosted.schedule_fixture) as scheduler:
            bundle = self.run_attempt(model)
        scheduler.assert_not_called()
        self.assertEqual(len(model.requests), 1)
        self.assertFalse(any(entry["event"] == "tool_proposal" for entry in bundle["trace"]))
        event = bundle["trace"][-1]
        self.assertEqual((event["status"], event["error_type"]), ("error", "incomplete_model_response"))
        self.assertEqual(event["agenda"], [])
        self.assertEqual(event["slots"], [])

    def test_mock_tool_timeout_is_logged_without_exception_text(self):
        diagnostic = "internal mock diagnostic"
        with patch.object(hosted, "schedule_fixture", side_effect=TimeoutError(diagnostic)) as scheduler:
            bundle = self.run_attempt(SyntheticModel())
        scheduler.assert_called_once_with(bundle["fixture"], mode="primary")
        self.assertFalse(any(obj["meta"]["source"] == "local_tool" for obj in bundle["objects"]))
        event = bundle["trace"][-1]
        self.assertEqual((event["status"], event["error_type"]), ("error", "runtime_TimeoutError"))
        self.assertEqual(event["agenda"], [])
        self.assertEqual(event["slots"], [])
        self.assertNotIn(diagnostic, json.dumps(bundle))
