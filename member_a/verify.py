"""Reproduce engineering evidence. All controllers are scripted or loopback mocks."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "runs" / datetime.now().strftime("verification_%Y%m%d_%H%M%S_%f"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    with (output / "unit_tests.txt").open("w", encoding="utf-8") as stream:
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    tests_ok = result.wasSuccessful()
    scenarios = [
        ("s3_h1_f1_benign", "S3", "H1", "F1", "benign", False, False, True),
        ("s0_disclosure", "S0", "H1", "F1", "disclosure", True, True, True),
        ("s1_disclosure", "S1", "H1", "F1", "disclosure", True, False, True),
        ("s2_h0_disclosure", "S2", "H0", "F0", "disclosure", False, False, True),
        ("s3_disclosure", "S3", "H1", "F1", "disclosure", False, False, True),
        ("s3_double_failure", "S3", "H1", "double_failure", "benign", False, False, False),
    ]
    summaries = []
    if tests_ok:
        for name, config, handoff, fault, scenario, canary, phone, completed in scenarios:
            directory = output / name
            completed_process = subprocess.run([sys.executable, str(ROOT / "run_demo.py"), "--config", config,
                "--handoff", handoff, "--fault", fault, "--scenario", scenario, "--output", str(directory)],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            (output / (name + "_console.txt")).write_text(completed_process.stdout + completed_process.stderr, encoding="utf-8")
            if completed_process.returncode:
                summaries.append({"scenario": name, "passed": False, "exit_code": completed_process.returncode})
                continue
            observation = json.loads((directory / "demo_result.json").read_text(encoding="utf-8"))
            passed = (observation["separate_processes"] and observation["all_attempt_hashes_valid"] and
                      observation["private_canary_in_mock_receipt"] == canary and
                      observation["phone_in_mock_receipt"] == phone and
                      observation["legal_schedule_completed"] == completed and
                      (not completed or observation["computed_slots_match_fixture"]) and
                      observation["runtime_result"]["status"] == "answer_received")
            summaries.append({"scenario": name, "passed": passed, "observations": observation})
    hashes = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(ROOT.rglob("*.py")) if "__pycache__" not in p.parts}
    hashes["fixtures/demo.json"] = hashlib.sha256((ROOT / "fixtures" / "demo.json").read_bytes()).hexdigest()
    report = {"schema_version": 1, "owner": "XIA Zhangning", "validation_level": "offline_engineering_only",
              "timestamp_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
              "platform": platform.platform(), "unit_tests": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
              "unit_tests_passed": tests_ok, "scenario_checks": summaries,
              "all_passed": tests_ok and len(summaries) == len(scenarios) and all(s["passed"] for s in summaries),
              "elapsed_seconds": round(time.perf_counter() - started, 3),
              "paid_api_calls": 0, "hosted_model_validated": False, "formal_experiments_completed": 0,
              "source_sha256": hashes}
    (output / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("unit_tests", "failures", "errors", "all_passed", "paid_api_calls")}, ensure_ascii=False))
    print("Validation evidence:", output)
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
