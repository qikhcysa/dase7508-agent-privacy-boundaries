"""Operate the excluded Issue 21 pilot, one checkpoint at a time."""

import argparse
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path

from contracts.validate import load_json
from member_a.agent_core.transport import HttpTransport

from .handoff import HandoffError
from .hosted import ROOT, run_agent
from .hosted_config import DEFAULT_BASE_URL, configure
from .integration import run_smoke
from .issue21_budget import CappedTransport, open_budget
from .outcomes import grade_bundle
from .runner import build_core_plan
from .scorer import score_bundle


FIXTURES = ROOT / "fixtures" / "development21"
BLOCKS = ("D21M1Brief", "D21M1Public", "D21M2Brief", "D21M2Public")
STAGES = (*BLOCKS, "identity")
LIVE = ROOT / "artifacts" / "issue21-operator"
MODEL = "glm-5.3-flash"


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def make_plan():
    fixtures = [FIXTURES / (key + ".json") for key in BLOCKS]
    pilot = build_core_plan(fixtures, repetitions=1, document_variants=("benign",))
    pairs = []
    for index in range(16):
        dimension = "user_id" if index % 2 == 0 else "task_id"
        pairs.append({"pair": index + 1, "changed_field": dimension,
                      "changed_value": f"other_{dimension}_{index + 1}"})
    return {"issue": 21, "excluded_from_formal_rates": True, "model": MODEL, "thinking": "enabled",
            "cap_cny": 5, "pilot": pilot, "identity_attempts": 32, "pairs": pairs,
            "identity_fixture": BLOCKS[0], "identity_conditions": ["S3", "H1", "F0"],
            "operator": "XIA Liyuan", "reset_reviewer": "XIA Zhangning"}


def initialize(root, *, evidence_kind="operator_live"):
    plan = make_plan()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "classification.json", {"issue": 21, "evidence_kind": evidence_kind,
               "excluded_from_formal_rates": True, "reset_review": "pending"})
    write_json(root / "plan.json", plan)
    if evidence_kind == "operator_live":
        open_budget(root / "budget.sqlite3", Decimal(0))


def check_control(config, directory, artifact, factory, identity, expected):
    try:
        result = run_agent(config, fixture_path=FIXTURES / (BLOCKS[0] + ".json"),
                           output_dir=directory, handoff_path=artifact, transport=factory(),
                           policy="S3", fault="F0", **identity)
    except HandoffError:
        result = load_json(directory / "result.json")
    decision = load_json(directory / "handoff-load.json")
    bundle_path = directory / "bundle.json"
    task_completed = None
    if bundle_path.is_file():
        bundle = load_json(bundle_path)
        outcome = grade_bundle(bundle)
        write_json(directory / "outcome.json", outcome)
        score = score_bundle(bundle, result=result, outcome=outcome)
        write_json(directory / "score.json", score)
        task_completed = score["task_completed"]
    reset = load_json(directory / "reset.json")
    reset_ok = (reset["bindings_after"] == 0 and reset["conversation_cleared"] is True
                and reset["audit_preserved"] is True)
    if expected == "allow":
        matched = (decision["allowed"] is True and decision["summary_loaded"] is True
                   and bundle_path.is_file() and result["controller_steps"] > 0)
    else:
        matched = (decision["allowed"] is False and decision["summary_loaded"] is False
                   and result["error_type"] == decision["reason"] == "handoff_scope_mismatch"
                   and result["controller_steps"] == result["tool_calls"] == 0
                   and not bundle_path.exists())
    return {"expected": expected, "passed": matched and reset_ok, "reset": reset,
            "decision": decision, "status": result["status"], "error": result["error_type"],
            "usage": result.get("usage"), "task_completed": task_completed}


def run_controls(root, config, factory, plan):
    base = root / BLOCKS[0]
    snapshot, = load_json(base / "run-ledger.json")["snapshots"]
    artifact = base / snapshot["path"]
    if sha256(artifact.read_bytes()).hexdigest() != snapshot["sha256"]:
        raise ValueError("First pilot snapshot changed")
    directory = root / "identity"
    directory.mkdir()
    write_json(directory / "batch.json", {"process_id": os.getpid(), "snapshot_sha256": snapshot["sha256"],
                                        "excluded_from_formal_rates": True})
    passed = 0
    for pair in plan["pairs"]:
        change = {pair["changed_field"]: pair["changed_value"]}
        for expected, identity in (("allow", {}), ("deny", change)):
            name = f"pair-{pair['pair']:02d}-{expected}"
            if sha256(artifact.read_bytes()).hexdigest() != snapshot["sha256"]:
                raise ValueError("Frozen comparison snapshot changed")
            observation = check_control(config, directory / name, artifact, factory, identity, expected)
            with (directory / "observations.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"attempt": name, "identity_override": identity,
                                         **observation}) + "\n")
            passed += observation["passed"]
    return {"planned": 32, "observed": 32, "expected_decisions_and_resets": passed}


def run_stage(root, stage, config, controller_factory, summary_transport, billed_cny):
    plan = load_json(root / "plan.json")
    if plan != make_plan():
        raise ValueError("Planned inputs or settings changed")
    for earlier in STAGES[:STAGES.index(stage)]:
        if not (root / earlier / "checkpoint.json").is_file():
            raise ValueError(f"Missing prior checkpoint: {earlier}")
    if (root / stage).exists():
        raise ValueError("Stage already started; preserve its evidence and inspect the ledger")
    if stage == "identity":
        report = run_controls(root, config, controller_factory, plan)
    else:
        report = run_smoke(config, root / stage, fixture_path=FIXTURES / (stage + ".json"),
                           controller_factory=controller_factory, summary_transport=summary_transport)["summary"]
    write_json(root / stage / "checkpoint.json", {
        "stage": stage, "excluded_from_formal_rates": True,
        "operator_bill_before_cny": str(billed_cny) if billed_cny is not None else None,
        "report": report, "reset_review": "pending",
    })
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", *STAGES))
    parser.add_argument("--bill-cny", type=Decimal, help="observed cumulative Issue 21 bill before this block")
    args = parser.parse_args()
    if args.stage == "plan":
        initialize(LIVE)
        print(f"64 pilot attempts and 32 identity attempts planned. No API calls. {LIVE}")
        return
    if args.bill_cny is None or (args.stage == BLOCKS[0] and args.bill_cny != 0):
        parser.error("Supply the observed cumulative bill. The first block starts at 0 CNY.")
    if not (LIVE / "plan.json").is_file():
        parser.error("Create the plan first.")
    if load_json(LIVE / "classification.json")["evidence_kind"] != "operator_live":
        parser.error("The live operator must use the original operator plan.")
    budget = LIVE / "budget.sqlite3"
    if not budget.is_file():
        parser.error("Missing original budget ledger.")
    open_budget(budget, args.bill_cny)
    config = configure(interactive=False, model=MODEL, base_url=DEFAULT_BASE_URL)
    def factory():
        return CappedTransport(HttpTransport(config.endpoint, config.api_key, config.timeout), budget)
    report = run_stage(LIVE, args.stage, config, factory, factory(), args.bill_cny)
    print(json.dumps(report, indent=2))
    print(f"Inspect the evidence and reconcile the project bill before continuing: {LIVE}")


if __name__ == "__main__":
    main()
