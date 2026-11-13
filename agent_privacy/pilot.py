"""T01 scripted mechanism pilot. This module does not call a language model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .fixture_loader import load_fixture as load_validated_fixture
from .registry import ObjectRecord, ObjectRegistry
from .release import Authorization, MockReceiver, ReleaseAdapter, ReleaseRequest
from .scheduler import feasible_slots

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "t01.json"


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    return load_validated_fixture(path)


def build_registry(fixture: dict[str, Any], slots: list[dict[str, str]]) -> ObjectRegistry:
    registry = ObjectRegistry()
    task_id = fixture["fixture_id"]
    organizer = fixture["contacts"]["entries"][0]
    registry.add(
        ObjectRecord(
            fixture["calendar"]["handle"], task_id, "synthetic-local-calendar", "private", False,
            {"events": fixture["calendar"]["events"]},
        )
    )
    registry.add(
        ObjectRecord(
            fixture["contacts"]["handle"], task_id, "synthetic-local-contacts", "private", False,
            {"name": organizer["name"], "phone": organizer["phone"]},
        )
    )
    registry.add(
        ObjectRecord(
            "schedule.slots", task_id, "trusted-local-scheduler", "conditional", True,
            {"slots": slots},
        )
    )
    return registry


def task_authorization(task_id: str) -> Authorization:
    return Authorization(
        active_task_id=task_id,
        allowed={"mock-cloud": {"schedule": {"schedule.slots": ("slots",)}}},
    )


def run_case(fixture: dict[str, Any], document_condition: str, configuration: str) -> dict[str, Any]:
    if document_condition not in {"benign", "attacked"}:
        raise ValueError("document_condition must be benign or attacked")
    task_id = fixture["fixture_id"]
    calendar_handle = fixture["calendar"]["handle"]
    slots = feasible_slots(fixture["candidate_slots"], fixture["calendar"]["events"])
    registry = build_registry(fixture, slots)
    receiver = MockReceiver()
    adapter = ReleaseAdapter(registry, task_authorization(task_id), configuration, receiver)
    paragraph = fixture["benign_paragraph"] if document_condition == "benign" else fixture["attack_paragraph"]
    document = fixture["document_common"] + "\n\n" + paragraph
    try:
        # The following request is deliberately scripted. It validates the release
        # boundary; it does not measure whether any real model obeys the document.
        if document_condition == "attacked":
            adapter.send(
                ReleaseRequest(
                    task_id, "schedule", "mock-cloud", calendar_handle, ("events",),
                    "scripted response to attacker paragraph",
                )
            )
        adapter.send(
            ReleaseRequest(
                task_id, "schedule", "mock-cloud", "schedule.slots", ("slots",),
                "scripted legal continuation",
            )
        )
        raw_released = any(record["object_id"] == calendar_handle for record in receiver.records)
        slots_received = any(record["object_id"] == "schedule.slots" for record in receiver.records)
        return {
            "fixture": task_id,
            "document_condition": document_condition,
            "configuration": configuration,
            "handoff": "H0_direct_document",
            "fault": "F0_normal_scheduler",
            "controller": "scripted_mechanism_probe_not_a_language_model",
            "document": document,
            "local_result": {"agenda": fixture["expected_agenda"], "slots": slots},
            "proposals": adapter.proposals,
            "decisions": adapter.decisions,
            "outgoing_requests": adapter.outgoing_requests,
            "receiver_records": receiver.records,
            "raw_calendar_actually_received": raw_released,
            "local_path_completed": bool(
                fixture["expected_agenda"] and slots == fixture["expected_slots"] and slots_received
            ),
        }
    finally:
        registry.close()


def run_pilot(fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    fixture = fixture or load_fixture()
    cases = [
        run_case(fixture, document, configuration)
        for document in ("benign", "attacked")
        for configuration in ("S0", "S3")
    ]
    return {
        "status": "mechanism_pilot_only_not_formal_experiment",
        "fixture": fixture["fixture_id"],
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/t01-pilot.json"))
    args = parser.parse_args()
    result = run_pilot()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for case in result["cases"]:
        print(
            case["document_condition"], case["configuration"],
            "raw_received=" + str(case["raw_calendar_actually_received"]),
            "local_path_completed=" + str(case["local_path_completed"]),
        )
    print("Trace:", args.output)


if __name__ == "__main__":
    main()
