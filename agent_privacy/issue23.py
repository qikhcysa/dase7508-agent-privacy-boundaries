"""Operate the frozen Issue 23 formal core one 32-condition block at a time."""

from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from contracts.validate import load_json
from member_a.agent_core.transport import HttpTransport

from .handoff import prepare_handoff
from .hosted import ROOT, run_agent
from .hosted_config import ConfigurationCancelled, DEFAULT_BASE_URL, configure
from .issue23_budget import (
    CappedTransport,
    budget_status,
    check_budget_evidence,
    initialize_budget,
    open_budget,
)
from .outcomes import grade_bundle
from .runner import build_core_plan, plan_sha256, run_plan
from .scorer import score_directory


MODEL = "glm-5.3-flash"
SEED = "dase7508-core-v1"
PROTOCOL_PATH = "docs/evaluation/ISSUE22_2026-11-23.md"
PROTOCOL_SHA256 = "996a654ebc6b0486015d767e856bffa3369401ad5dc5de90639eff9c4aba86f3"
PLAN_SHA256 = "8dad8653fd61e4282d1c9dc8838aa78eae731234847a124d6237e901268c3497"
LIVE = ROOT / "artifacts" / "issue23-operator"
CORE = LIVE / "core"
BLOCK_SIZE = 32


def _write_json(path: Path, value, *, replace=False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    if path.exists() and not replace:
        temporary.unlink()
        raise ValueError(f"Refusing to replace existing evidence: {path}")
    temporary.replace(path)


def _git(*args: str) -> bytes:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        raise ValueError("Git evidence is unavailable") from None


def protocol_sha256() -> str:
    digest = hashlib.sha256(_git("cat-file", "blob", f"HEAD:{PROTOCOL_PATH}")).hexdigest()
    if digest != PROTOCOL_SHA256:
        raise ValueError("The approved protocol blob changed")
    return digest


def execution_commit(*, require_clean: bool) -> str:
    commit = _git("rev-parse", "HEAD").decode("ascii").strip()
    if require_clean and _git("status", "--porcelain", "--untracked-files=all").strip():
        raise ValueError("Formal execution requires a clean committed checkout")
    return commit


def frozen_plan() -> dict:
    plan = build_core_plan(repetitions=3, seed=SEED)
    if plan_sha256(plan) != PLAN_SHA256:
        raise ValueError("The frozen core plan digest changed")
    return plan


def initialize(root: Path = LIVE) -> dict:
    protocol = protocol_sha256()
    plan = frozen_plan()
    root.mkdir(parents=True, exist_ok=False)
    _write_json(root / "classification.json", {
        "issue": 23,
        "phase": "formal",
        "model": MODEL,
        "protocol_path": PROTOCOL_PATH,
        "protocol_sha256": protocol,
        "plan_sha256": PLAN_SHA256,
        "attempts": plan["attempt_count"],
        "block_size": BLOCK_SIZE,
        "operator": "XIA Liyuan",
        "retry_limit": 0,
    })
    _write_json(root / "frozen-plan.json", plan)
    initialize_budget(root / "budget.sqlite3")
    return plan


def _metadata(commit: str) -> dict:
    return {
        "issue": 23,
        "phase": "formal",
        "protocol_sha256": PROTOCOL_SHA256,
        "execution_commit": commit,
        "model": MODEL,
        "retry_limit": 0,
    }


def _score() -> dict:
    report = score_directory(CORE)
    _write_json(LIVE / "score.json", report, replace=True)
    return report


def run_next_block(*, formal_bill_cny: Decimal, daily_bill_cny: Decimal,
                   project_bill_cny: Decimal, interactive: bool = True) -> dict:
    if not (LIVE / "classification.json").is_file():
        raise ValueError("Initialize the Issue 23 operator plan first")
    classification = load_json(LIVE / "classification.json")
    if (classification.get("protocol_sha256") != protocol_sha256()
            or classification.get("plan_sha256") != PLAN_SHA256):
        raise ValueError("Frozen Issue 23 metadata changed")
    plan = load_json(LIVE / "frozen-plan.json")
    if plan != frozen_plan():
        raise ValueError("Frozen Issue 23 plan changed")
    commit = execution_commit(require_clean=True)
    budget = LIVE / "budget.sqlite3"
    check_budget_evidence(budget)
    open_budget(
        budget,
        formal_bill_cny=formal_bill_cny,
        daily_bill_cny=daily_bill_cny,
        project_bill_cny=project_bill_cny,
    )
    existing = 0
    if CORE.exists():
        ledger = load_json(CORE / "run-ledger.json")
        if ledger.get("metadata") != _metadata(commit):
            raise ValueError("Execution commit or frozen formal metadata changed")
        existing = len(ledger["attempts"])
    if existing >= plan["attempt_count"]:
        raise ValueError("All frozen Issue 23 conditions are already recorded")
    remaining = BLOCK_SIZE - (existing % BLOCK_SIZE)
    config = configure(
        interactive=interactive,
        model=MODEL,
        base_url=DEFAULT_BASE_URL,
        timeout=120,
        max_tokens=8192,
        max_steps=8,
        max_tool_calls=16,
    )

    def transport():
        return CappedTransport(
            HttpTransport(config.endpoint, config.api_key, config.timeout), budget
        )

    def snapshot_provider(condition, directory):
        return prepare_handoff(
            config,
            fixture_path=ROOT / condition["fixture_path"],
            cache_dir=directory,
            document_variant=condition["document_variant"],
            repetition=condition["repetition"],
            transport=transport(),
            phase="formal",
            protocol_sha256=PROTOCOL_SHA256,
        )

    def execute(condition, directory, snapshot):
        result = run_agent(
            config,
            fixture_path=ROOT / condition["fixture_path"],
            output_dir=directory,
            handoff_path=snapshot,
            document_variant=condition["document_variant"],
            repetition=condition["repetition"],
            fault=condition["fault"],
            policy=condition["policy"],
            transport=transport(),
            phase="formal",
            protocol_sha256=PROTOCOL_SHA256,
        )
        outcome = grade_bundle(load_json(directory / "bundle.json"))
        _write_json(directory / "outcome.json", outcome)
        return result

    def after_condition(record):
        check_budget_evidence(budget)
        if record["preparation_error"] is not None:
            raise ValueError(f"Review snapshot evidence for {record['attempt_key']}")
        if (len(record["executions"]) != 1
                or record["executions"][0]["reset_ok"] is not True):
            raise ValueError(f"Review reset evidence for {record['attempt_key']}")

    failure = None
    try:
        ledger = run_plan(
            plan,
            CORE,
            execute,
            snapshot_provider=snapshot_provider,
            after_condition=after_condition,
            max_retries=0,
            retryable_errors=(),
            resume=CORE.exists(),
            max_new_conditions=remaining,
            metadata=_metadata(commit),
        )
    except Exception as exc:
        failure = exc
        ledger = load_json(CORE / "run-ledger.json") if (CORE / "run-ledger.json").is_file() else None
    report = _score() if ledger is not None else None
    if failure is not None:
        raise failure
    observed = len(ledger["attempts"])
    if observed % BLOCK_SIZE:
        raise ValueError("Formal execution stopped before a complete 32-condition block")
    block = plan["blocks"][observed // BLOCK_SIZE - 1]
    checkpoint = {
        "issue": 23,
        "phase": "formal",
        "block_id": block["block_id"],
        "attempts_recorded": observed,
        "protocol_sha256": PROTOCOL_SHA256,
        "execution_commit": commit,
        "operator_bills_before_cny": {
            "formal": str(formal_bill_cny),
            "daily": str(daily_bill_cny),
            "project": str(project_bill_cny),
        },
        "budget_after": budget_status(budget),
        "score_summary": report["summary"],
        "next_action": "reconcile_provider_bill_before_next_block",
    }
    _write_json(LIVE / "checkpoints" / f"{block['block_id']}.json", checkpoint)
    return checkpoint


def status() -> dict:
    plan = load_json(LIVE / "frozen-plan.json")
    attempts = 0
    finished = False
    if (CORE / "run-ledger.json").is_file():
        ledger = load_json(CORE / "run-ledger.json")
        attempts = len(ledger["attempts"])
        finished = ledger["finished_at"] is not None
    return {
        "planned_attempts": plan["attempt_count"],
        "recorded_attempts": attempts,
        "complete_blocks": attempts // BLOCK_SIZE,
        "conditions_in_current_block": attempts % BLOCK_SIZE,
        "finished": finished,
        "budget": budget_status(LIVE / "budget.sqlite3"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan", help="freeze the local operator plan; no API calls")
    block = subparsers.add_parser("block", help="run or finish the next 32-condition block")
    block.add_argument("--formal-bill-cny", type=Decimal, required=True)
    block.add_argument("--daily-bill-cny", type=Decimal, required=True)
    block.add_argument("--project-bill-cny", type=Decimal, required=True)
    block.add_argument("--non-interactive", action="store_true")
    subparsers.add_parser("status", help="print saved progress; no API calls")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            plan = initialize()
            result = {"planned_attempts": plan["attempt_count"], "blocks": plan["block_count"],
                      "api_calls": 0, "evidence": str(LIVE)}
        elif args.command == "status":
            result = status()
        else:
            result = run_next_block(
                formal_bill_cny=args.formal_bill_cny,
                daily_bill_cny=args.daily_bill_cny,
                project_bill_cny=args.project_bill_cny,
                interactive=not args.non_interactive,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ConfigurationCancelled:
        print("Cancelled; no new request started.", file=sys.stderr)
        return 130
    except (OSError, ValueError, KeyboardInterrupt) as exc:
        print(f"Issue 23 stopped: {exc}", file=sys.stderr)
        print(f"Preserve and inspect evidence under {LIVE}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
