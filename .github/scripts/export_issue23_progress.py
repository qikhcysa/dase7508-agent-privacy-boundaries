#!/usr/bin/env python3
"""Export a privacy-safe, reviewable snapshot of the live Issue 23 run."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
import sqlite3
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
UNITS_PER_CNY = 10_000_000


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def block_id(row: dict) -> str:
    return f"{row['fixture_id']}-r{row['repetition']}"


def budget_snapshot(path: Path) -> dict:
    with sqlite3.connect(path) as db:
        total, pending = db.execute(
            "SELECT COALESCE(SUM(units),0), COALESCE(SUM(pending),0) FROM usage"
        ).fetchone()
        states = dict(db.execute(
            "SELECT state, COUNT(*) FROM usage GROUP BY state ORDER BY state"
        ).fetchall())
        operator = db.execute(
            "SELECT formal_bill_units, project_bill_units, daily_bill_units, "
            "shanghai_day FROM operator_snapshot WHERE singleton=1"
        ).fetchone()
        try:
            reconciliations = db.execute(
                "SELECT COUNT(*) FROM operator_reconciliation"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            reconciliations = 0
    return {
        "local_conservative_cny": str(total / UNITS_PER_CNY),
        "pending_requests": pending,
        "usage_states": states,
        "operator_bill_snapshot_cny": {
            "formal": str(operator[0] / UNITS_PER_CNY),
            "project": str(operator[1] / UNITS_PER_CNY),
            "daily": str(operator[2] / UNITS_PER_CNY),
            "shanghai_day": operator[3],
        },
        "operator_reconciliations": reconciliations,
    }


def percent(part: int, whole: int) -> str:
    return "0.0%" if not whole else f"{part / whole:.1%}"



TARGET_CONFIRMED = "confirmed_success"
TARGET_UNCONFIRMED = "outbound_delivery_unconfirmed"


def summarize_target_outcomes(items) -> dict:
    """Count the labels the grader actually emits (never target_disclosure_observed)."""
    confirmed = sum(1 for item in items if item["target_outcome"] == TARGET_CONFIRMED)
    unconfirmed = sum(1 for item in items if item["target_outcome"] == TARGET_UNCONFIRMED)
    return {
        "target_confirmed": confirmed,
        "target_unconfirmed": unconfirmed,
        "target_disclosures": confirmed + unconfirmed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    live = args.source.resolve()
    output = args.output.resolve()
    ledger_path = live / "core" / "run-ledger.json"
    score_path = live / "score.json"
    plan_path = live / "frozen-plan.json"
    budget_path = live / "budget.sqlite3"
    ledger = load(ledger_path)
    score = load(score_path)
    plan = load(plan_path)
    summary = score["summary"]
    observed = [row for row in score["attempts"] if row.get("observed")]
    ledger_rows = {row["attempt_key"]: row for row in ledger["attempts"]}
    generated = datetime.now(SHANGHAI).isoformat(timespec="seconds")

    rows = []
    for row in observed:
        key = row["planned_attempt_key"]
        record = ledger_rows.get(key, {})
        executions = record.get("executions") or []
        selected = next(
            (item for item in executions if item.get("try") == record.get("selected_try")),
            executions[0] if executions else {},
        )
        rows.append({
            "ordinal": next((x.get("ordinal") for x in ledger["attempts"] if x["attempt_key"] == key), ""),
            "group": block_id(row),
            "attempt_key": key,
            "fixture": row["fixture_id"],
            "repetition": row["repetition"],
            "variant": row["document_variant"],
            "policy": row["policy"],
            "handoff": row["handoff"],
            "fault": row["fault"],
            "status": row["status"],
            "task_completed": bool(row.get("task_completed")),
            "error_type": row.get("error_type") or "",
            "reset_ok": selected.get("reset_ok"),
            "valid_evidence": bool(row.get("valid_evidence")),
            "target_outcome": row.get("target_outcome") or "",
            "privacy_labels": ";".join(row.get("privacy_labels") or []),
            "overblocked": row["overblocked"],
            "evidence_path": row.get("evidence_path") or "",
        })

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["group"]].append(row)
    block_order = [block["block_id"] for block in plan["blocks"]]
    block_rows = []
    for name in block_order:
        items = grouped.get(name)
        if not items:
            continue
        errors = Counter(item["error_type"] for item in items if item["error_type"])
        block_rows.append({
            "group": name,
            "recorded": len(items),
            "complete_group": len(items) == 32,
            "completed": sum(item["task_completed"] for item in items),
            "errors": sum(errors.values()),
            "invalid_json": errors["invalid_json"],
            "transport_error": errors["transport_error"],
            "reset_failures": sum(item["reset_ok"] is not True for item in items),
            "delivery_unknown": sum("delivery_unknown" in item["privacy_labels"] for item in items),
            **summarize_target_outcomes(items),
            "overblocked": sum(item["overblocked"] is True for item in items),
        })

    policy_rows = []
    for policy in ("S0", "S1", "S2", "S3"):
        items = [row for row in rows if row["policy"] == policy]
        policy_rows.append({
            "policy": policy,
            "recorded": len(items),
            "completed": sum(item["task_completed"] for item in items),
            "errors": sum(bool(item["error_type"]) for item in items),
            **summarize_target_outcomes(items),
            "overblocked": sum(item["overblocked"] is True for item in items),
        })

    planned_attempts = plan["attempt_count"]
    recorded_attempts = len(rows)
    complete_blocks = recorded_attempts // 32
    complete_run = recorded_attempts == planned_attempts
    snapshot = {
        "schema_version": "issue23-live-progress-v1",
        "preliminary": not complete_run,
        "generated_at_shanghai": generated,
        "execution_commit": ledger["metadata"]["execution_commit"],
        "protocol_sha256": ledger["metadata"]["protocol_sha256"],
        "planned_attempts": planned_attempts,
        "recorded_attempts": recorded_attempts,
        "complete_blocks": complete_blocks,
        "planned_blocks": plan["block_count"],
        "progress": recorded_attempts / planned_attempts,
        "observed_summary": {
            "completed_attempts": sum(row["task_completed"] for row in rows),
            "status_counts": dict(Counter(row["status"] for row in rows)),
            "error_type_counts": dict(Counter(row["error_type"] for row in rows if row["error_type"])),
            "privacy_label_counts": dict(Counter(label for row in rows for label in row["privacy_labels"].split(";") if label)),
            "target_outcome_counts": dict(Counter(row["target_outcome"] for row in rows if row["target_outcome"])),
            "overblocked_attempts": sum(row["overblocked"] is True for row in rows),
            "authorized_requests": summary["overblocking"]["authorized_requests"],
            "blocked_authorized_requests": summary["overblocking"]["blocked_authorized_requests"],
            "unknown_requests": summary["overblocking"]["unknown_requests"],
            "unknown_benign_attempts": summary["overblocking"]["unknown_benign_attempts"],
            "invalid_evidence": summary["invalid_evidence"],
        },
        "budget": budget_snapshot(budget_path),
        "groups": block_rows,
        "policies": policy_rows,
        "source_digests": {
            "run_ledger_sha256": digest(ledger_path),
            "score_sha256": digest(score_path),
            "frozen_plan_sha256": digest(plan_path),
        },
    }

    observed_summary = snapshot["observed_summary"]
    lines = [
        "# Issue 23 final formal results" if complete_run else "# Issue 23 live formal progress",
        "",
        ("> Final derived snapshot: all frozen attempts are recorded and scored."
         if complete_run else
         "> Preliminary, incomplete evidence. This branch updates after every two additional complete 32-attempt groups. Missing planned attempts are not failures."),
        "",
        f"Generated: `{generated}` (Asia/Shanghai)  ",
        f"Execution commit: `{snapshot['execution_commit']}`  ",
        f"Protocol: `{snapshot['protocol_sha256']}`",
        "",
        "## Current snapshot",
        "",
        f"- Progress: **{recorded_attempts}/{planned_attempts} ({percent(recorded_attempts, planned_attempts)})**; complete groups: **{complete_blocks}/{plan['block_count']}**.",
        f"- Completed tasks: **{observed_summary['completed_attempts']}/{recorded_attempts}**.",
        f"- Errors: `{json.dumps(observed_summary['error_type_counts'], ensure_ascii=False, sort_keys=True)}`.",
        f"- Target outcomes: `{json.dumps(observed_summary['target_outcome_counts'], ensure_ascii=False, sort_keys=True)}`.",
        f"- Privacy labels: `{json.dumps(observed_summary['privacy_label_counts'], ensure_ascii=False, sort_keys=True)}`.",
        f"- Authorized requests blocked: **{observed_summary['blocked_authorized_requests']}/{observed_summary['authorized_requests']}**; overblocked attempts: **{observed_summary['overblocked_attempts']}**.",
        f"- Requests with unknown overblocking: **{observed_summary['unknown_requests']}**. "
        f"Benign attempts with unknown overblocking: **{observed_summary['unknown_benign_attempts']}**.",
        f"- Invalid evidence: **{len(observed_summary['invalid_evidence'])}**.",
        f"- Local conservative budget usage: **{snapshot['budget']['local_conservative_cny']} CNY**; pending requests: **{snapshot['budget']['pending_requests']}**.",
        "",
        "Target disclosures count only `confirmed_success` and `outbound_delivery_unconfirmed`; `no_target_disclosure_observed` means no disclosure was observed in retained evidence, and it is not proof of universal safety. `delivery_unknown` remains uncertainty and is not promoted to a safe result.",
        "",
        "## Results by 32-attempt group",
        "",
        "| Group | Recorded | Complete | Tasks completed | Errors | invalid_json | transport_error | Reset failures | delivery_unknown | Target confirmed | Target unconfirmed | Overblocked |",
        "|---|---:|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in block_rows:
        lines.append(
            f"| {row['group']} | {row['recorded']} | {'yes' if row['complete_group'] else 'no'} | "
            f"{row['completed']} | {row['errors']} | {row['invalid_json']} | {row['transport_error']} | "
            f"{row['reset_failures']} | {row['delivery_unknown']} | {row['target_confirmed']} | {row['target_unconfirmed']} | {row['overblocked']} |"
        )
    lines += [
        "",
        "## Results by policy",
        "",
        "| Policy | Recorded | Tasks completed | Errors | Target confirmed | Target unconfirmed | Overblocked |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in policy_rows:
        lines.append(
            f"| {row['policy']} | {row['recorded']} | {row['completed']} | {row['errors']} | "
            f"{row['target_confirmed']} | {row['target_unconfirmed']} | {row['overblocked']} |"
        )
    lines += [
        "",
        "## Files",
        "",
        "The [operator archive manifest](../ARCHIVE.md) describes the underlying records and their verification status.",
        "",
        "- `live-attempts.csv`: one row per recorded formal attempt, including group, S/H/F condition, completion, error type, reset status and outcome labels.",
        "- `live-progress.json`: machine-readable aggregate, budget snapshot and source digests.",
        "- Raw conversations, request bodies, API credentials and local SQLite files are intentionally not published on this branch.",
        "",
    ]
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as temporary:
        staging = Path(temporary)
        md_path = staging / "README.md"
        md_path.write_text("\n".join(lines), encoding="utf-8")
        json_path = staging / "live-progress.json"
        json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        csv_path = staging / "live-attempts.csv"
        fieldnames = list(rows[0]) if rows else ["ordinal", "group", "attempt_key", "status", "error_type"]
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        publish_files(output, (csv_path, json_path, md_path))
    print(json.dumps({
        "recorded_attempts": recorded_attempts,
        "complete_blocks": complete_blocks,
        "output": str(output),
    }, ensure_ascii=False))
    return 0


def publish_files(output, staged_files):
    # Keep the previous snapshot available if a destination cannot be replaced.
    previous = {}
    for staged in staged_files:
        destination = output / staged.name
        if destination.exists():
            backup = staged.with_suffix(".backup")
            copyfile(destination, backup)
            previous[destination] = backup
    replaced = []
    try:
        for staged in staged_files:
            destination = output / staged.name
            staged.replace(destination)
            replaced.append(destination)
    except (OSError, KeyboardInterrupt):
        for destination in reversed(replaced):
            if destination in previous:
                previous[destination].replace(destination)
            else:
                destination.unlink()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
