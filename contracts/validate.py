"""Validate shared interface examples offline; validation does not grant authority."""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import best_match

ROOT = Path(__file__).resolve().parent
KINDS = ("bundle", "fixture", "authorization", "object_metadata", "registry_object",
         "tool_proposal", "release_request", "run", "handoff", "trace_event", "byte_evidence")
CHECKER = FormatChecker(formats=[])


class ContractError(ValueError):
    """An interface or evidence-consistency violation, without echoing data."""


@CHECKER.checks("date-time")
def _timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return True  # The schema's type keyword reports this case.
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None
    except ValueError:
        return False


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("JSON contains a duplicate object key")
        result[key] = value
    return result


def _constant(_value: str) -> None:
    raise ContractError("JSON contains a non-finite numeric constant")


def load_json(path: str | Path) -> Any:
    """Parse JSON strictly; duplicate keys cannot silently replace authority."""
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=_unique_pairs, parse_constant=_constant)


@lru_cache(maxsize=None)
def _validator(kind: str) -> Draft202012Validator:
    if kind not in KINDS:
        raise ContractError("Unknown contract kind")
    schema = load_json(ROOT / "v1" / "schema.json")
    Draft202012Validator.check_schema(schema)
    schema["$ref"] = "#/$defs/" + kind
    # All references stay in this committed schema; no remote retrieval is needed.
    return Draft202012Validator(schema, format_checker=CHECKER)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _bytes(record: dict) -> bytes:
    try:
        raw = base64.b64decode(record["base64"], validate=True)
    except (binascii.Error, ValueError):
        raise ContractError("Byte evidence has invalid Base64") from None
    _require(base64.b64encode(raw).decode("ascii") == record["base64"], "Byte evidence is not canonical Base64")
    _require(len(raw) == record["byte_length"], "Byte evidence length mismatch")
    _require(hashlib.sha256(raw).hexdigest() == record["sha256"], "Byte evidence digest mismatch")
    return raw


def _slots(slots: list[dict]) -> None:
    for slot in slots:
        start = datetime.fromisoformat(slot["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(slot["end"].replace("Z", "+00:00"))
        _require(start < end, "Time interval must end after it starts")


def _event_evidence(event: dict) -> None:
    if event["event"] in {"send_attempt", "receiver_record"}:
        _bytes(event["body"])
    elif event["event"] == "send_result" and event["response"] is not None:
        _bytes(event["response"])
    elif event["event"] == "run_finished":
        _slots(event["slots"])


def _bundle(data: dict) -> None:
    run, fixture = data["run"], data["fixture"]
    _require(run["fixture_id"] == fixture["fixture_id"], "Run/fixture ID mismatch")
    _require(data["authorization"]["scope"] == run["scope"], "Authorization scope differs from active run")
    _slots(fixture["candidate_slots"] + fixture["expected_slots"] + fixture["calendar"]["events"])
    records = {record["handle"]: record for record in data["objects"]}
    _require(len(records) == len(data["objects"]), "Duplicate object handle")

    def selection(handle: str, fields: list[str]) -> None:
        _require(handle in records, "Selection references an unknown handle")
        _require(set(fields) <= records[handle]["value"].keys(), "Selection references an unknown field")

    for handle in data["authorization"]["context_handles"]:
        _require(handle in records, "Context authorization references an unknown handle")
    for grant in data["authorization"]["grants"]:
        selection(grant["handle"], grant["fields"])
    for record in records.values():
        for parent in record["meta"]["derivation"]:
            _require(parent in records, "Self-contained bundle is missing a derivation parent")
    visited, active = set(), set()

    def lineage(handle: str) -> None:
        _require(handle not in active, "Cyclic object derivation")
        if handle in visited:
            return
        active.add(handle)
        for parent in records[handle]["meta"]["derivation"]:
            lineage(parent)
        active.remove(handle)
        visited.add(handle)
    for handle in records:
        lineage(handle)

    handoff = data["handoff"]
    _require((run["handoff"] == "H1") == (handoff is not None), "Handoff condition/artifact mismatch")
    if handoff is not None:
        _require(all(handoff[key] == run[key] for key in ("fixture_id", "document_variant", "repetition")),
                 "Frozen handoff artifact belongs to a different fixture/variant/repetition")
        handle = handoff["summary_handle"]
        _require(handle in records and records[handle]["meta"]["source"] == "model_summary", "Handoff summary metadata is missing")
        generation = handoff["generation"]
        _require((generation["controller_mode"] == "scripted") == (generation["model"] is None),
                 "Handoff generation mode/model mismatch")

    event_ids, proposal_ids = set(), set()
    calls, requests, decisions, load_decisions, egress, sends, results, receipts = {}, {}, {}, {}, {}, {}, set(), set()
    finished = False
    for event in data["trace"]:
        _require(not finished, "Events follow run_finished")
        _require(event["event_id"] not in event_ids, "Duplicate event ID")
        event_ids.add(event["event_id"])
        _require(event["attempt_id"] == run["attempt_id"] and event["scope"] == run["scope"], "Event scope differs from active run")
        _event_evidence(event)
        kind = event["event"]
        if kind == "tool_proposal":
            call, proposal = event["call_id"], event["proposal"]
            _require(call not in calls and proposal["proposal_id"] not in proposal_ids, "Duplicate call/proposal ID")
            calls[call] = proposal
            proposal_ids.add(proposal["proposal_id"])
        elif kind == "release_request":
            request = event["request"]
            key = request["request_id"]
            _require(key not in requests, "Duplicate release request ID")
            proposal = calls.get(request["call_id"])
            _require(proposal is not None and proposal["name"] == "release", "Release request lacks an earlier release proposal")
            _require(all(request[k] == proposal["arguments"][k] for k in ("handle", "fields", "recipient")), "Normalized request differs from proposed selection")
            _require(request["scope"] == run["scope"] and request["purpose"] == run["purpose"], "Release scope/purpose differs from runtime context")
            selection(request["handle"], request["fields"])
            requests[key] = request
        elif kind == "policy_decision":
            reference = event["reference_id"]
            if event["operation"] == "release":
                _require(reference in requests and reference not in decisions, "Decision needs one earlier, undecided release request")
                decisions[reference] = event["allowed"]
            else:
                _require(reference in records, "Load decision references an unknown handle")
                load_decisions[reference] = event["allowed"]
        elif kind == "context_loaded":
            handle = event["handle"]
            _require(handle in records and load_decisions.get(handle) is True, "Loaded context lacks an earlier allowed load decision")
            _require(event["source_metadata"] == records[handle]["meta"], "Loading rewrote original source metadata")
        elif kind == "egress_decision":
            key = event["send_id"]
            _require(key not in egress, "Duplicate egress decision for send ID")
            for item in event["selections"]:
                selection(item["handle"], item["fields"])
            egress[key] = event
        elif kind == "send_attempt":
            key = event["send_id"]
            _require(key not in sends, "Duplicate send ID")
            gate = egress.get(key)
            _require(gate is not None and gate["allowed"] is True, "Send lacks its own earlier allowed egress decision")
            _require(all(event[k] == gate[k] for k in ("recipient", "channel", "selections")) and
                     event["body"]["sha256"] == gate["body_sha256"], "Egress decision is bound to a different payload")
            for item in event["selections"]:
                selection(item["handle"], item["fields"])
            if event["channel"] == "release":
                request_id = event["request_id"]
                _require(request_id in requests and decisions.get(request_id) is True, "Send lacks an earlier allowed release decision")
                request = requests[request_id]
                _require(event["recipient"] == request["recipient"], "Send recipient differs from release request")
                _require(event["selections"] == [{"handle": request["handle"], "fields": request["fields"]}], "Release send has inconsistent selection metadata")
            else:
                _require(event["recipient"] == "controller" and event["request_id"] is None, "Controller send has an invalid envelope")
            sends[key] = event
        elif kind == "receiver_record":
            send = sends.get(event["send_id"])
            _require(send is not None and send["recipient"] == "mock_cloud", "Receiver record lacks a matching cloud send attempt")
            _require(event["body"] == send["body"], "Receiver bytes differ from attempted request")
            receipts.add(event["send_id"])
        elif kind == "send_result":
            key = event["send_id"]
            send = sends.get(key)
            _require(send is not None and key not in results, "Result needs one earlier, unmatched send attempt")
            _require(event["transport_mode"] == send["transport_mode"], "Transport mode changed between attempt and result")
            if event["delivery"] == "delivery_unknown":
                _require(event["response"] is None and event["status"] is None and event["error_type"] is not None, "Unknown delivery cannot claim an observed response")
            else:
                expected = {"http": "http_response_observed", "scripted": "scripted_response_observed", "in_process_mock": "mock_receipt_observed"}
                _require(event["delivery"] == expected[event["transport_mode"]] and event["response"] is not None and event["status"] is not None, "Observation does not match actual transport")
                if event["delivery"] == "mock_receipt_observed":
                    _require(key in receipts, "Mock reception claim lacks matching receiver bytes")
            results.add(key)
        elif kind == "run_finished":
            finished = True
            if event["status"] == "error":
                _require(event["error_type"] is not None, "Error outcome needs an error type")
            if event["status"] == "completed":
                _require(bool(event["agenda"]) and bool(event["slots"]) and event["error_type"] is None, "Completed outcome needs agenda, slots and no execution error")
    # Unfinished traces and unknown-delivery attempts remain representable.
    # Policy effectiveness and correctness of agenda/slots belong to later scorers.


def validate(kind: str, instance: Any) -> None:
    """Check shape, then local consistency; never execute tools or change input."""
    try:
        json.dumps(instance, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ContractError("Input is not finite JSON data") from None
    error = best_match(_validator(kind).iter_errors(instance))
    if error is not None:
        path = "$" + "".join(f"[{part}]" if isinstance(part, int) else "." + part for part in error.absolute_path)
        raise ContractError(f"Schema violation at {path} ({error.validator})")
    if kind == "bundle":
        _bundle(instance)
    elif kind == "fixture":
        _slots(instance["candidate_slots"] + instance["expected_slots"] + instance["calendar"]["events"])
    elif kind == "trace_event":
        _event_evidence(instance)
    elif kind == "byte_evidence":
        _bytes(instance)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, nargs="*")
    parser.add_argument("--kind", choices=KINDS, default="bundle")
    args = parser.parse_args(argv)
    paths = args.paths or sorted((ROOT / "examples").glob("*.json"))
    for path in paths:
        try:
            validate(args.kind, load_json(path))
        except (ContractError, OSError, UnicodeError, json.JSONDecodeError) as error:
            print(f"INVALID {path.name}: {type(error).__name__}: {error}", file=sys.stderr)
            return 1
        print(f"VALID {args.kind}: {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
