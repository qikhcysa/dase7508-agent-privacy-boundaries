"""Verify the Issue 22 input lock offline, without running model attempts."""

import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path

from agent_privacy.runner import plan_sha256, validate_plan
from contracts.validate import load_json


ROOT = Path(__file__).resolve().parents[1]
CORE_SHA256 = "8dad8653fd61e4282d1c9dc8838aa78eae731234847a124d6237e901268c3497"
LOCKED_INPUTS = {
    "contracts/v1/schema.json": "a565e723b72e971029551f25eea284f3de42e99f61330195c3a000eae5c8eca7",
    "fixtures/benign/allowed_fields.json": "90f9fd90781af7a96072363afbefc5045b20ed600d617997b4eb0a189c077acb",
    "fixtures/attacks/criteria.json": "7b3bd4570e87c653d66d6f218ffce287a8cba5dab6a3cee3dc29750149a59a53",
    "fixtures/supplements/cases.json": "376fcee2215d30adf88e0b76755500f169602c252d70900ccbc4e6a7f9718c25",
}


def verify(plan_path: Path) -> None:
    plan = load_json(plan_path)
    if plan_sha256(plan) != CORE_SHA256:
        raise ValueError("Core plan differs from the dated Issue 22 protocol.")
    validate_plan(plan)
    for filename, expected in LOCKED_INPUTS.items():
        if sha256((ROOT / filename).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Input differs from the dated Issue 22 protocol: {filename}")

    snapshots = {
        row["handoff_snapshot_key"]
        for block in plan["blocks"]
        for row in block["attempts"]
        if row["handoff"] == "H1"
    }
    cases = load_json(ROOT / "fixtures/supplements/cases.json")["cases"]
    attempts = Counter()
    for case in cases:
        attempts[case["family"]] += case.get("attempts", 1)
    print(f"Core: {plan['attempt_count']} attempts, {plan['block_count']} blocks, "
          f"{len(snapshots)} H1 snapshots.")
    print(f"Supplements: {len(cases)} entries, {sum(attempts.values())} attempts "
          f"({dict(sorted(attempts.items()))}).")
    print(f"Total planned attempts: {plan['attempt_count'] + sum(attempts.values())}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    try:
        verify(args.plan)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
