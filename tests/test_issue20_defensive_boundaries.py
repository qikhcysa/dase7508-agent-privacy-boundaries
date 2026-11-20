"""Test production local boundaries without a provider, transport or runner."""

import unittest
from copy import deepcopy

from agent_privacy.scheduler import schedule_fixture, verify_schedule_result
from agent_privacy.static_allowlist import StaticAllowlist


def slot(hour):
    return {"start": f"2026-01-01T{hour}:00:00Z", "end": f"2026-01-01T{hour}:30:00Z"}


class DefensiveProductionBoundaries(unittest.TestCase):
    def setUp(self):
        self.fixture = {
            "candidate_slots": [slot("01"), slot("02"), slot("03"), slot("04"), slot("05")],
            "calendar": {"events": [slot("01")]},
            "meeting_minutes": 30,
        }

    def test_primary_and_local_recovery_have_same_capped_output(self):
        original = deepcopy(self.fixture)
        expected = {"slots": [slot("02"), slot("03"), slot("04")]}
        self.assertEqual(schedule_fixture(self.fixture, "primary"), expected)
        self.assertEqual(schedule_fixture(self.fixture, "recovery"), expected)
        self.assertEqual(self.fixture, original)

    def test_no_free_slot_or_wrong_duration_returns_empty(self):
        self.fixture["candidate_slots"] = [slot("01"), dict(slot("02"), end="2026-01-01T02:15:00Z")]
        self.assertEqual(schedule_fixture(self.fixture), {"slots": []})

    def test_result_validator_rejects_extra_metadata_and_unavailable_slot(self):
        candidates = self.fixture["candidate_slots"]
        events = self.fixture["calendar"]["events"]
        with self.assertRaisesRegex(ValueError, "only start and end"):
            verify_schedule_result({"slots": [dict(slot("02"), label="synthetic")]},
                                   candidates, events, 30)
        with self.assertRaisesRegex(ValueError, "fixture constraints"):
            verify_schedule_result({"slots": [slot("01")]}, candidates, events, 30)

    def test_release_rules_are_snapshotted_and_fail_closed(self):
        rules = {"public_slots": ["start", "end"]}
        policy = StaticAllowlist(rules)
        rules["public_slots"].append("label")
        self.assertEqual(policy.decide([{"handle": "public_slots", "fields": ["start", "end"]}]),
                         (True, "s2_allowlisted"))
        self.assertEqual(policy.decide([{"handle": "public_slots", "fields": ["label"]}]),
                         (False, "s2_field_not_allowlisted"))
        self.assertEqual(policy.decide([{"handle": "other", "fields": ["start"]}]),
                         (False, "s2_object_not_allowlisted"))
