"""Boundary checks for the T01 mechanism pilot."""

import json
import unittest

from agent_privacy.pilot import build_registry, load_fixture, run_case, run_pilot, task_authorization
from agent_privacy.registry import ObjectRecord, ObjectRegistry
from agent_privacy.release import Authorization, MockReceiver, ReleaseAdapter, ReleaseRequest
from agent_privacy.scheduler import feasible_slots


class PilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = load_fixture()

    def test_pair_changes_only_the_attacker_controlled_paragraph(self) -> None:
        benign = run_case(self.fixture, "benign", "S3")["document"]
        attacked = run_case(self.fixture, "attacked", "S3")["document"]
        self.assertEqual(benign.split("\n\n")[0], attacked.split("\n\n")[0])
        self.assertNotEqual(benign.split("\n\n")[1], attacked.split("\n\n")[1])

    def test_local_schedule_excludes_busy_interval(self) -> None:
        slots = feasible_slots(self.fixture["candidate_slots"], self.fixture["calendar"]["events"])
        self.assertEqual(len(slots), 3)
        self.assertNotIn(self.fixture["candidate_slots"][1], slots)
        self.assertEqual(slots, self.fixture["expected_slots"])

    def test_s3_rejects_raw_release_before_transmission_but_keeps_task_path(self) -> None:
        case = run_case(self.fixture, "attacked", "S3")
        self.assertFalse(case["raw_calendar_actually_received"])
        self.assertTrue(case["local_path_completed"])
        self.assertEqual(case["decisions"][0]["reason"], "private_object_not_authorized")
        self.assertEqual(len(case["outgoing_requests"]), 1)
        self.assertEqual(case["receiver_records"][0]["object_id"], "schedule.slots")

    def test_s0_actual_send_and_receiver_record_match(self) -> None:
        case = run_case(self.fixture, "attacked", "S0")
        self.assertTrue(case["raw_calendar_actually_received"])
        sent = [json.loads(item["serialized"]) for item in case["outgoing_requests"]]
        self.assertEqual(sent, case["receiver_records"])
        self.assertEqual(sent[0]["fields"]["events"][0]["title"], "SYNTHETIC-PRIVATE-CALENDAR-CANARY-42")

    def test_active_task_and_original_object_task_are_checked(self) -> None:
        slots = feasible_slots(self.fixture["candidate_slots"], self.fixture["calendar"]["events"])
        registry = build_registry(self.fixture, slots)
        receiver = MockReceiver()
        adapter = ReleaseAdapter(registry, task_authorization("T02"), "S3", receiver)
        try:
            decision = adapter.send(ReleaseRequest("T02", "schedule", "mock-cloud", "schedule.slots", ("slots",)))
            self.assertEqual(decision["reason"], "object_task_mismatch")
            self.assertEqual(receiver.records, [])
        finally:
            registry.close()

    def test_explicit_lawful_private_field_can_be_shared(self) -> None:
        slots = feasible_slots(self.fixture["candidate_slots"], self.fixture["calendar"]["events"])
        registry = build_registry(self.fixture, slots)
        receiver = MockReceiver()
        authorization = Authorization(
            "T01", {"mock-cloud": {"contact-confirmation": {"contacts.organizer": ("phone",)}}}
        )
        adapter = ReleaseAdapter(registry, authorization, "S3", receiver)
        try:
            decision = adapter.send(
                ReleaseRequest("T01", "contact-confirmation", "mock-cloud", "contacts.organizer", ("phone",))
            )
            self.assertTrue(decision["allowed"])
            self.assertEqual(receiver.records[0]["fields"], {"phone": "SYNTHETIC-PRIVATE-PHONE-555-0100"})
        finally:
            registry.close()

    def test_invalid_requests_are_recorded_without_transmission(self) -> None:
        slots = feasible_slots(self.fixture["candidate_slots"], self.fixture["calendar"]["events"])
        registry = build_registry(self.fixture, slots)
        base = {
            "task_id": "T01", "purpose": "schedule", "recipient": "mock-cloud",
            "object_id": "schedule.slots", "fields": ("slots",),
        }
        cases = [
            ({"task_id": "T02"}, "request_task_mismatch"),
            ({"purpose": "debug"}, "recipient_purpose_or_field_not_authorized"),
            ({"recipient": "other-cloud"}, "unsupported_pilot_recipient"),
            ({"object_id": "missing"}, "unknown_object"),
            ({"fields": ()}, "unknown_or_empty_field"),
            ({"fields": ("missing",)}, "unknown_or_empty_field"),
        ]
        try:
            for changes, expected in cases:
                with self.subTest(changes=changes):
                    receiver = MockReceiver()
                    adapter = ReleaseAdapter(registry, task_authorization("T01"), "S3", receiver)
                    request = ReleaseRequest(**{**base, **changes})
                    decision = adapter.send(request)
                    self.assertFalse(decision["allowed"])
                    self.assertEqual(decision["reason"], expected)
                    self.assertEqual(len(adapter.proposals), 1)
                    self.assertEqual(adapter.decisions, [decision])
                    self.assertEqual(adapter.outgoing_requests, [])
                    self.assertEqual(receiver.records, [])
        finally:
            registry.close()

    def test_mixed_fields_cannot_expand_explicit_private_authorization(self) -> None:
        slots = feasible_slots(self.fixture["candidate_slots"], self.fixture["calendar"]["events"])
        registry = build_registry(self.fixture, slots)
        receiver = MockReceiver()
        authorization = Authorization(
            "T01", {"mock-cloud": {"contact-confirmation": {"contacts.organizer": ("phone",)}}}
        )
        adapter = ReleaseAdapter(registry, authorization, "S3", receiver)
        try:
            decision = adapter.send(ReleaseRequest(
                "T01", "contact-confirmation", "mock-cloud", "contacts.organizer", ("phone", "name")
            ))
            self.assertEqual(decision["reason"], "private_object_not_authorized")
            self.assertEqual(adapter.outgoing_requests, [])
            self.assertEqual(receiver.records, [])
        finally:
            registry.close()

    def test_authorized_conditional_fields_still_require_trusted_derivation(self) -> None:
        registry = ObjectRegistry()
        registry.add(ObjectRecord(
            "untrusted.slots", "T01", "attacker-document", "conditional", False,
            {"slots": self.fixture["candidate_slots"][:1]},
        ))
        authorization = Authorization(
            "T01", {"mock-cloud": {"schedule": {"untrusted.slots": ("slots",)}}}
        )
        receiver = MockReceiver()
        adapter = ReleaseAdapter(registry, authorization, "S3", receiver)
        try:
            decision = adapter.send(ReleaseRequest(
                "T01", "schedule", "mock-cloud", "untrusted.slots", ("slots",)
            ))
            self.assertEqual(decision["reason"], "untrusted_derivation")
            self.assertEqual(adapter.outgoing_requests, [])
            self.assertEqual(receiver.records, [])
        finally:
            registry.close()

    def test_pilot_has_four_declared_mechanism_cases(self) -> None:
        cases = run_pilot(self.fixture)["cases"]
        self.assertEqual(len(cases), 4)
        self.assertEqual({case["controller"] for case in cases}, {"scripted_mechanism_probe_not_a_language_model"})
        self.assertTrue(all(case["local_path_completed"] for case in cases))


if __name__ == "__main__":
    unittest.main()
