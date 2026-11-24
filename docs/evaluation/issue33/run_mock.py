"""Run the Issue #33 draft's one benign T01 trial with an in-process mock."""

import argparse
import json
from pathlib import Path

from agent_privacy.hosted import run_agent
from agent_privacy.hosted_config import HostedConfig
from agent_privacy.outcomes import grade_bundle
from agent_privacy.runner import build_core_plan, run_plan
from contracts.validate import load_json
from tests.test_hosted import SyntheticModel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    fixture = Path("fixtures/t01.json")
    plan = build_core_plan(
        [fixture],
        repetitions=1,
        seed="dase7508-issue33-mock-v1",
        policies=("S0",),
        handoffs=("H0",),
        faults=("F0",),
        document_variants=("benign",),
    )
    config = HostedConfig(
        api_key="placeholder_offline_only",
        base_url="https://offline.invalid",
        model="offline-placeholder",
    )

    def execute(condition, directory, snapshot):
        result = run_agent(
            config,
            fixture_path=fixture,
            output_dir=directory,
            transport=SyntheticModel(),
            handoff_path=snapshot,
            document_variant=condition["document_variant"],
            repetition=condition["repetition"],
            fault=condition["fault"],
            policy=condition["policy"],
        )
        outcome = grade_bundle(load_json(directory / "bundle.json"))
        (directory / "outcome.json").write_text(
            json.dumps(outcome, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return result

    ledger = run_plan(plan, args.output_dir, execute)
    attempt, = ledger["attempts"]
    execution, = attempt["executions"]
    print(f"{attempt['condition']['attempt_key']}: {execution['status']}")
    print(f"Evidence: {args.output_dir / execution['output_dir']}")
    return int(execution["status"] != "completed")


if __name__ == "__main__":
    raise SystemExit(main())
