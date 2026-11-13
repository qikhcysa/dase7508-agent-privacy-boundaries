"""Paired component observations for the documented S1 comparator."""

import base64
from copy import deepcopy
import json
from pathlib import Path

from contracts.validate import ROOT, load_json, validate
from member_a.agent_core.transport import ScriptedTransport

from .egress import EgressAdapter
from .redaction import PHONE_REPLACEMENT, RULE_VERSION
from .scoped_registry import ScopedRegistry


def run_demo(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    observations = []
    for fault in ("F0", "F1"):
        for policy in ("S0", "S1"):
            folder = directory / (policy + fault)
            folder.mkdir()
            bundle = load_json(ROOT / "examples" / "benign-h0.json")
            bundle["run"].update(policy=policy, fault=fault)
            bundle["run"]["attempt_id"] = "s1_component_" + policy + fault
            phone = "+852 87654321"
            bundle["fixture"]["contacts"]["entries"][0]["phone"] = phone
            bundle["objects"][2]["value"]["entries"][0]["phone"] = phone
            snapshot = deepcopy(bundle["objects"])
            with ScopedRegistry() as registry:
                for record in bundle["objects"]:
                    registry.put_record(record)
                controller = ScriptedTransport([{}])
                adapter = EgressAdapter(bundle["run"], registry, controller=controller,
                                        trace_path=folder / "events.jsonl")
                selection = {"handle": "contacts.organizer", "fields": ["entries"]}
                adapter.send_controller({"messages": [{"role": "user", "content": json.dumps(
                    bundle["objects"][2]["value"])}]}, selections=[selection])
                for call, handle, fields in (("phone", "contacts.organizer", ["entries"]),
                                             ("slots", "schedule.slots", ["slots"]),
                                             ("limit", "calendar.raw", ["events"])):
                    adapter.record_proposal(call, {"proposal_id": call, "name": "release", "arguments": {
                        "handle": handle, "fields": fields, "recipient": "mock_cloud"}})
                    adapter.release_to_cloud(call)
                for record in snapshot:
                    if registry.inspect_record(record["handle"])["value"] != record["value"]:
                        raise AssertionError("Original registry data changed.")
            bundle["trace"] = [json.loads(line) for line in adapter.trace_path.read_text(encoding="utf8").splitlines()]
            validate("bundle", bundle)
            (folder / "bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
            sends = [event for event in bundle["trace"] if event["event"] == "send_attempt"]
            bodies = [base64.b64decode(event["body"]["base64"]) for event in sends]
            redacted = all(b"87654321" not in body and PHONE_REPLACEMENT.encode() in body for body in bodies[:2])
            slots_preserved = json.loads(bodies[2])["fields"]["slots"] == bundle["fixture"]["expected_slots"]
            known_leak = b"SYNTHETIC_PRIVATE_EVENT" in bodies[3]
            if redacted != (policy == "S1") or not slots_preserved or not known_leak:
                raise AssertionError("Component observations differ from the declared comparator.")
            observations.append({"policy": policy, "fault_input": fault, "phone_redacted_both_paths": redacted,
                                 "legal_slots_preserved": slots_preserved, "known_event_title_leak": known_leak,
                                 "send_count": len(sends), "bundle": str(folder / "bundle.json")})
    report = {"rule_version": RULE_VERSION, "stage": "development_component_probe",
              "paid_model_calls": 0, "observations": observations}
    (directory / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    return report
