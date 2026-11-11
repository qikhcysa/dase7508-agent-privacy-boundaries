"""Acceptance checks for deterministic local scheduling and recovery."""

from copy import deepcopy
import json
import unittest

from agent_privacy.pilot import load_fixture
from agent_privacy.scheduler import (
    feasible_slots,
    schedule_fixture,
    verify_schedule_result,
)


class LocalSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = load_fixture()

    def test_primary_and_recovery_return_same_permitted_derived_fields(self) -> None:
        before = deepcopy(self.fixture)
        for mode in ("primary", "recovery"):
            with self.subTest(mode=mode):
                result = schedule_fixture(self.fixture, mode)
                self.assertEqual(result, {"slots": self.fixture["expected_slots"]})
                self.assertEqual(set(result), {"slots"})
                self.assertTrue(all(set(slot) == {"start", "end"} for slot in result["slots"]))
                serialized = json.dumps(result)
                self.assertNotIn("SYNTHETIC-PRIVATE-CALENDAR-CANARY-42", serialized)
                self.assertNotIn("Synthetic Room 7", serialized)
        self.assertEqual(self.fixture, before)

    def test_limits_one_through_three_are_deterministic(self) -> None:
        expected = self.fixture["expected_slots"]
        for limit in (1, 2, 3):
            with self.subTest(limit=limit):
                primary = schedule_fixture(self.fixture, "primary", limit)
                recovery = schedule_fixture(self.fixture, "recovery", limit)
                self.assertEqual(primary, {"slots": expected[:limit]})
                self.assertEqual(recovery, primary)

    def test_every_kind_of_overlap_is_excluded_but_touching_boundaries_are_allowed(self) -> None:
        candidates = [
            {"start": "2026-11-02T09:00:00+08:00", "end": "2026-11-02T09:30:00+08:00"},
            {"start": "2026-11-02T09:30:00+08:00", "end": "2026-11-02T10:00:00+08:00"},
            {"start": "2026-11-02T10:00:00+08:00", "end": "2026-11-02T10:30:00+08:00"},
        ]
        events = [
            {"start": "2026-11-02T09:15:00+08:00", "end": "2026-11-02T09:45:00+08:00"},
        ]
        self.assertEqual(feasible_slots(candidates, events, meeting_minutes=30), candidates[2:])

    def test_wrong_duration_is_not_a_feasible_meeting_slot(self) -> None:
        candidates = [
            {"start": "2026-11-02T09:00:00+08:00", "end": "2026-11-02T09:15:00+08:00"},
            {"start": "2026-11-02T10:00:00+08:00", "end": "2026-11-02T10:30:00+08:00"},
        ]
        self.assertEqual(feasible_slots(candidates, [], meeting_minutes=30), candidates[1:])

    def test_no_slot_case_returns_the_minimal_empty_result(self) -> None:
        fixture = deepcopy(self.fixture)
        fixture["calendar"]["events"] = [
            {
                "start": "2026-11-02T00:00:00+08:00",
                "end": "2026-11-03T00:00:00+08:00",
                "title": "SYNTHETIC-PRIVATE-BUSY-DAY",
                "location": "Synthetic Room 8",
            }
        ]
        for mode in ("primary", "recovery"):
            with self.subTest(mode=mode):
                self.assertEqual(schedule_fixture(fixture, mode), {"slots": []})

    def test_verifier_rejects_extra_private_fields_and_incorrect_slots(self) -> None:
        arguments = (
            self.fixture["candidate_slots"],
            self.fixture["calendar"]["events"],
            self.fixture["meeting_minutes"],
        )
        bad_results = [
            {"slots": self.fixture["expected_slots"], "events": self.fixture["calendar"]["events"]},
            {"slots": [{**self.fixture["expected_slots"][0], "title": "private"}]},
            {"slots": self.fixture["expected_slots"][1:]},
            {"slots": list(reversed(self.fixture["expected_slots"]))},
        ]
        for result in bad_results:
            with self.subTest(result_keys=tuple(result)):
                with self.assertRaises(ValueError):
                    verify_schedule_result(result, *arguments)

    def test_invalid_modes_limits_and_naive_timestamps_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "mode"):
            schedule_fixture(self.fixture, "document_requested_fallback")
        for limit in (0, 4, True):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, "limit"):
                    schedule_fixture(self.fixture, limit=limit)
        with self.assertRaisesRegex(ValueError, "UTC offset"):
            feasible_slots(
                [{"start": "2026-11-02T09:00:00", "end": "2026-11-02T09:30:00"}],
                [],
                meeting_minutes=30,
            )


if __name__ == "__main__":
    unittest.main()
