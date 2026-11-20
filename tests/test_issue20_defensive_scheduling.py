"""Defensive offline scheduling smoke checks; no real model or transport."""

import unittest
from unittest.mock import Mock

from agent_privacy.scheduler import schedule_fixture
from contracts.validate import validate
from test_issue20_defensive_trace import synthetic


def ready(slot_hour, **extra):
    return {
        "start": f"2026-01-01T{slot_hour}:00:00Z",
        "end": f"2026-01-01T{slot_hour}:30:00Z",
        **extra,
    }


def run_public_agenda(provider, scheduler, fixture):
    """Test-only composition of a fake provider and the local scheduler."""
    try:
        agenda = provider()
        if agenda is None:
            return synthetic(
                "run_finished", status="incomplete", agenda=[], slots=[],
                error_type="ProviderRefused",
            )
        slots = scheduler(fixture)["slots"]
        return synthetic(
            "run_finished", status="completed" if slots else "incomplete",
            agenda=agenda, slots=slots, error_type=None,
        )
    except TimeoutError:
        return synthetic(
            "run_finished", status="error", agenda=[], slots=[],
            error_type="TimeoutError",
        )


class DefensiveSchedulingSmoke(unittest.TestCase):
    def setUp(self):
        self.fixture = {
            "candidate_slots": [ready("01"), ready("02", label="synthetic notes")],
            "calendar": {"events": [ready("01", title="synthetic busy event")]},
            "meeting_minutes": 30,
        }

    def test_benign_slots_and_log_exclude_private_metadata(self):
        provider = Mock(return_value=["Review tomorrow's agenda"])
        event = run_public_agenda(provider, schedule_fixture, self.fixture)
        validate("trace_event", event)
        provider.assert_called_once_with()
        self.assertEqual(event["status"], "completed")
        self.assertEqual(event["slots"], [ready("02")])
        self.assertNotIn("synthetic notes", str(event))
        self.assertNotIn("synthetic busy event", str(event))

    def test_refused_provider_never_calls_scheduler(self):
        scheduler = Mock(wraps=schedule_fixture)
        event = run_public_agenda(Mock(return_value=None), scheduler, self.fixture)
        validate("trace_event", event)
        self.assertEqual((event["status"], event["error_type"], event["slots"]),
                         ("incomplete", "ProviderRefused", []))
        scheduler.assert_not_called()

    def test_mock_tool_timeout_is_logged_without_exception_text(self):
        scheduler = Mock(side_effect=TimeoutError("internal mock diagnostic"))
        event = run_public_agenda(Mock(return_value=["Review agenda"]), scheduler, self.fixture)
        validate("trace_event", event)
        self.assertEqual((event["status"], event["error_type"], event["slots"]),
                         ("error", "TimeoutError", []))
        self.assertNotIn("internal mock diagnostic", str(event))
