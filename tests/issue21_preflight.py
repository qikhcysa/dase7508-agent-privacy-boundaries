"""Keep replayable, benign evidence for the Issue 21 offline handoff."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from agent_privacy.handoff import HandoffError
from agent_privacy.hosted import run_agent
from agent_privacy.hosted_config import HostedConfig
from agent_privacy.integration import FIXTURE, run_smoke
from contracts.validate import load_json, validate
from member_a.agent_core.transport import TransportError
from tests.test_handoff import SummaryModel, summary_reply
from tests.test_hosted import SyntheticModel


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def check_identity(config, artifact, directory, **identity):
    model = SyntheticModel()
    error = None
    try:
        run_agent(config, output_dir=directory, transport=model, policy="S3",
                  handoff_path=artifact, **identity)
    except HandoffError as exc:
        error = str(exc)
    load = load_json(directory / "handoff-load.json")
    reset = load_json(directory / "reset.json")
    result = load_json(directory / "result.json")
    passed = (error == load["reason"] == result["error_type"] == "handoff_scope_mismatch"
              and load["allowed"] is False and load["summary_loaded"] is False
              and result["controller_steps"] == result["tool_calls"] == len(model.requests) == 0
              and reset["bindings_after"] == 0 and reset["conversation_cleared"] is True
              and reset["audit_preserved"] is True)
    return {"changed": identity, "error": error, "scripted_requests": len(model.requests),
            "load": load, "reset": reset, "passed": passed}


def check_transport_error(config, directory):
    def unavailable(_payload, _step):
        raise TransportError("induced offline failure")

    result = run_agent(config, transport=SyntheticModel(unavailable), policy="S3",
                       output_dir=directory)
    bundle = load_json(directory / "bundle.json")
    validate("bundle", bundle)
    deliveries = [event["delivery"] for event in bundle["trace"] if event["event"] == "send_result"]
    return {"error": result["error_type"], "deliveries": deliveries, "usage": result["usage"],
            "reset": result["reset"],
            "passed": (result["status"] == "error" and result["error_type"] == "transport_error"
                       and deliveries == ["delivery_unknown"])}


def run(directory):
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "classification.json", {
        "issue": 21, "evidence_kind": "offline_preflight", "fixture_variant": "benign",
        "excluded_from_formal_rates": True, "counts_toward_64": False,
        "counts_toward_32": False, "transport": "scripted", "human_reset_review": "pending",
    })
    config = HostedConfig(api_key="unused-offline-placeholder")
    agenda = load_json(FIXTURE)["expected_agenda"]
    # Deliberately omit two facts. The scripted final answer still gives all three.
    summary = SummaryModel(summary_reply(agenda[0]))
    matrix = directory / "matrix"
    scores = run_smoke(config, matrix, controller_factory=SyntheticModel, summary_transport=summary)
    ledger = load_json(matrix / "run-ledger.json")
    snapshot, = ledger["snapshots"]
    artifact = matrix / snapshot["path"]
    summary_text = load_json(artifact.parent / "generation-result.json")["summary_text"]
    retained = [fact for fact in agenda if fact in summary_text]
    attempts = []
    for entry in ledger["attempts"]:
        execution, = entry["executions"]
        folder = matrix / execution["output_dir"]
        reset = load_json(folder / "reset.json")
        result = load_json(folder / "result.json")
        run_scope = load_json(folder / "run.json")["scope"]
        disk_reset_ok = (result["reset"] == reset and reset["bindings_after"] == 0
                         and reset["conversation_cleared"] is True and reset["audit_preserved"] is True
                         and (folder / "events.jsonl").stat().st_size > 0)
        attempts.append({"condition": entry["attempt_key"], "directory": execution["output_dir"],
                         "bundle_sha256": sha256((folder / "bundle.json").read_bytes()).hexdigest(),
                         "status": execution["status"], "error": execution["error_type"],
                         "session": run_scope["session_id"], "trial": run_scope["trial_id"],
                         "tool_calls": result["tool_calls"],
                         "reset_ok": execution["reset_ok"] and disk_reset_ok,
                         "reset": reset})
    diagnostics = {field: check_identity(config, artifact, directory / field, **{field: value})
                   for field, value in (("user_id", "other_user"), ("task_id", "other_task"))}
    failure = check_transport_error(config, directory / "transport-error")
    checks = {
        "matrix": (len(attempts) == scores["summary"]["completed_attempts"] == 16
                   and all(row["valid_evidence"] for row in scores["attempts"])
                   and not scores["summary"]["invalid_evidence"]),
        "all_resets": all(row["reset_ok"] for row in attempts),
        "unique_trials_and_sessions": all(len({row[key] for row in attempts}) == 16
                                          for key in ("trial", "session")),
        "one_generation": len(summary.requests) == 1,
        "loss_visible_in_summary": retained == [agenda[0]] and len(agenda) == 3,
        "mismatched_identities_denied": all(row["passed"] for row in diagnostics.values()),
        "failed_send_preserved": failure["passed"],
    }
    write_json(directory / "observations.json", {
        "classification": load_json(directory / "classification.json"),
        "checks": checks, "fixture_sha256": sha256(FIXTURE.read_bytes()).hexdigest(),
        "snapshot_sha256": snapshot["sha256"], "summary_text": summary_text,
        "retained_agenda": retained, "omitted_agenda": [fact for fact in agenda if fact not in retained],
        "score_summary": scores["summary"], "attempts": attempts,
        "identity_diagnostics": diagnostics, "transport_failure": failure,
    })
    return all(checks.values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="new directory for excluded offline evidence")
    raise SystemExit(0 if run(parser.parse_args().directory) else 1)
