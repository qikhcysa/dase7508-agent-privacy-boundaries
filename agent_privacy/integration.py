"""Run and score the Issue #20 development smoke matrix for one benign fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from contracts.validate import load_json

from .handoff import prepare_handoff
from .hosted import ROOT, run_agent
from .hosted_config import ConfigurationCancelled, configure
from .outcomes import grade_bundle
from .runner import build_core_plan, run_plan
from .scorer import score_directory


FIXTURE = ROOT / "fixtures" / "t01.json"


def run_smoke(config, output_dir: str | Path, *, controller_factory=None, summary_transport=None):
    """Use a fresh controller for each condition and share the frozen H1 input."""
    output_dir = Path(output_dir).resolve()
    plan = build_core_plan([FIXTURE], repetitions=1, document_variants=("benign",))

    def snapshot_provider(condition, directory):
        return prepare_handoff(config, fixture_path=FIXTURE, cache_dir=directory,
                               repetition=condition["repetition"], transport=summary_transport)

    def execute(condition, directory, snapshot):
        result = run_agent(
            config, fixture_path=FIXTURE, output_dir=directory, handoff_path=snapshot,
            repetition=condition["repetition"], fault=condition["fault"],
            policy=condition["policy"],
            transport=controller_factory() if controller_factory is not None else None,
        )
        outcome = grade_bundle(load_json(directory / "bundle.json"))
        (directory / "outcome.json").write_text(
            json.dumps(outcome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result

    run_plan(plan, output_dir, execute, snapshot_provider=snapshot_provider)
    report = score_directory(output_dir)
    (output_dir / "score.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", help="Requested model ID")
    parser.add_argument("--non-interactive", action="store_true", help="Read the key from the environment")
    args = parser.parse_args(argv)
    try:
        config = configure(model=args.model, interactive=not args.non_interactive)
        report = run_smoke(config, args.output_dir)
    except ConfigurationCancelled:
        return 130
    except (OSError, ValueError):
        print("Could not complete the smoke matrix. Check configuration and the evidence directory.",
              file=sys.stderr)
        return 2
    summary = report["summary"]
    print(f"{summary['completed_attempts']} of {summary['planned_attempts']} tasks completed")
    print(f"Score report: {args.output_dir / 'score.json'}")
    return int(summary["completed_attempts"] != summary["planned_attempts"]
               or any(row["valid_evidence"] is not True for row in report["attempts"]))


if __name__ == "__main__":
    raise SystemExit(main())
