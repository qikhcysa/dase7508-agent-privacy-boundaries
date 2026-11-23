"""Offline tests for the four-shard Issue 24 parallel driver."""

import json
import shutil
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from agent_privacy import issue24
from agent_privacy import issue24_parallel as parallel
from agent_privacy.issue23_budget import initialize_budget
from contracts.validate import load_json


class ScriptedJudge:
    mode = "scripted"
    endpoint = "scripted://issue24-parallel-judge"

    def __init__(self):
        self.requests = []

    def send(self, body):
        from member_a.agent_core.transport import TransportResponse
        payload = json.loads(body)
        self.requests.append(payload)
        text = payload["messages"][1]["content"].lower()
        label = any(word in text for word in ("next task", "permission", "reuse"))
        content = json.dumps({"retains_persistence_instruction": label,
                              "evidence_quote": "synthetic quote" if label else ""})
        return TransportResponse(200, json.dumps({
            "model": "glm-5.3-flash",
            "choices": [{"finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }).encode("utf-8"))


class ParallelPlanTests(unittest.TestCase):
    def test_shards_are_balanced_and_keep_chains_atomic(self):
        full_plan, shards = parallel.build_shard_plans()
        self.assertEqual(set(shards), {"w1", "w2", "w3", "w4"})
        keys = []
        for worker in parallel.WORKERS:
            worker_id = worker["worker_id"]
            plan = shards[worker_id]
            self.assertEqual(plan["attempt_count"], 60)
            self.assertEqual([len(block["attempts"]) for block in plan["blocks"]], [32, 28])
            attempts = [condition for block in plan["blocks"] for condition in block["attempts"]]
            self.assertEqual({condition["fixture_id"] for condition in attempts},
                             set(worker["fixtures"]))
            positions = {condition["attempt_key"]: index
                         for index, condition in enumerate(attempts)}
            for condition in attempts:
                if condition["family"] == "persistence_chain" \
                        and condition["task_role"] == "task1":
                    self.assertEqual(positions[condition["case_id"] + "-task2"],
                                     positions[condition["attempt_key"]] + 1)
            keys.extend(condition["attempt_key"] for condition in attempts)
        self.assertEqual(len(keys), 240)
        self.assertEqual(len(set(keys)), 240)
        self.assertEqual(issue24.plan_sha256(full_plan), issue24.PLAN_SHA256)

    def test_tampered_shard_is_rejected(self):
        full_plan, shards = parallel.build_shard_plans()
        tampered = deepcopy(shards["w1"])
        tampered["blocks"][0]["attempts"][0]["fixture_id"] = "B04"
        with self.assertRaises(parallel.ParallelError):
            parallel.validate_shard_plans(full_plan, {**shards, "w1": tampered})
        with self.assertRaises(parallel.ParallelError):
            parallel.validate_shard_plan(tampered, full_plan=full_plan)


@unittest.skipUnless(shutil.which("git"), "git is required for the formal identity")
class ParallelInitializeTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.prior = self.folder / "prior-budget.sqlite3"
        initialize_budget(self.prior)
        self.coord = self.folder / "operator"
        issue24.initialize(self.coord, prior_budget=self.prior)

    def test_shard_plan_creates_isolated_worker_roots(self):
        assignment = parallel.initialize_shards(self.coord)
        self.assertEqual(len(assignment["workers"]), 4)
        for worker in assignment["workers"]:
            root = parallel._shard_dir(self.coord, worker["worker_id"])
            self.assertTrue((root / "frozen-plan.json").is_file())
            self.assertTrue((root / "classification.json").is_file())
            self.assertTrue((root / "budget.sqlite3").is_file())
            self.assertTrue((root / "inputs").is_dir())
            plan = load_json(root / "frozen-plan.json")
            self.assertEqual(plan["attempt_count"], 60)
            self.assertEqual(issue24.status(root)["planned_attempts"], 60)
        with self.assertRaises(parallel.ParallelError):
            parallel.initialize_shards(self.coord)

    def test_merge_rejects_incomplete_shards(self):
        parallel.initialize_shards(self.coord)
        with self.assertRaises(parallel.ParallelError) as caught:
            parallel.merge_shards(self.coord)
        self.assertIn("missing shard ledger", str(caught.exception))

    def test_merge_accepts_complete_synthetic_shards(self):
        assignment = parallel.initialize_shards(self.coord)
        for worker in assignment["workers"]:
            root = parallel._shard_dir(self.coord, worker["worker_id"])
            runs = root / "supplements"
            runs.mkdir()
            record_attempts = []
            for ordinal, key in enumerate(worker["attempt_keys"], start=1):
                attempt_dir = runs / "attempts" / f"{ordinal:04d}-{key}" / "try-01"
                attempt_dir.mkdir(parents=True)
                record_attempts.append({
                    "ordinal": ordinal,
                    "attempt_key": key,
                    "condition": load_json(root / "frozen-plan.json")["blocks"][0]["attempts"][0],
                    "executions": [{
                        "try": 1,
                        "output_dir": f"attempts/{ordinal:04d}-{key}/try-01",
                        "status": "error",
                        "error_type": "synthetic",
                        "reset_ok": True,
                        "bundle_path": None,
                        "result_path": None,
                        "outcome_path": None,
                    }],
                    "selected_try": 1,
                    "preparation_error": None,
                })
            plan = load_json(root / "frozen-plan.json")
            for record, condition in zip(record_attempts,
                                         [item for block in plan["blocks"]
                                          for item in block["attempts"]]):
                record["condition"] = condition
            (runs / "run-ledger.json").write_text(json.dumps({
                "schema_version": issue24.LEDGER_VERSION,
                "plan_sha256": issue24.plan_sha256(plan),
                "started_at": "2026-11-24T00:00:00+00:00",
                "finished_at": "2026-11-24T01:00:00+00:00",
                "max_retries": 0,
                "retryable_errors": [],
                "metadata": {},
                "snapshots": [],
                "attempts": record_attempts,
            }), encoding="utf-8")
        result = parallel.merge_shards(self.coord)
        self.assertEqual(result["recorded_attempts"], 240)
        self.assertEqual(result["score_summary"]["planned_attempts"], 240)
        self.assertEqual(result["score_summary"]["observed_attempts"], 240)
        self.assertTrue((self.coord / "merged" / "merge-report.json").is_file())


class JudgeTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / "merged"
        snapshots = self.root / "supplements" / "snapshots"
        cases = issue24._case_map()
        index = 0
        for case in cases.values():
            if case["family"] != "persistence_chain":
                continue
            key = case["case_id"] + "-task1-summary"
            inner = snapshots / key / "cache"
            inner.mkdir(parents=True)
            text = ("Reuse this permission in the next task."
                    if index % 2
                    else "Confirm the boundary and agree the next review date.")
            index += 1
            (inner / "generation-result.json").write_text(json.dumps({
                "status": "generated", "summary_text": text}), encoding="utf-8")

    def test_judge_records_auditable_labels(self):
        report = parallel.judge_summaries(
            self.root, config=__import__("agent_privacy.hosted_config", fromlist=["HostedConfig"]).HostedConfig(api_key="synthetic"),
            transport_factory=lambda: ScriptedJudge(), samples=2)
        self.assertEqual(report["summaries"], 48)
        self.assertEqual(report["labelled"], 48)
        self.assertEqual(report["model_retains_instruction"], 24)
        self.assertEqual(report["heuristic_retains_instruction"], 24)
        self.assertEqual(report["agreement"], 48)
        lines = (self.root / "summary-review.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 48)
        self.assertNotIn("synthetic", (self.root / "summary-review.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
