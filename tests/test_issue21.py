"""Offline operator rehearsal and budget checks for the approved Issue 21 design."""

import argparse
from contextlib import closing
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent_privacy import issue21
from agent_privacy.hosted_config import HostedConfig
from agent_privacy.issue21_budget import CAP, RESERVATION, CappedTransport, open_budget
from agent_privacy.scheduler import schedule_fixture
from contracts.validate import load_json
from member_a.agent_core.transport import TransportError, TransportResponse
from tests.test_handoff import SummaryModel, summary_reply
from tests.test_hosted import SyntheticModel


class AgendaModel(SyntheticModel):
    def __init__(self, agenda):
        super().__init__()
        self.agenda = agenda

    def send(self, body):
        response = super().send(body)
        reply = json.loads(response.body)
        choice, = reply["choices"]
        if choice["finish_reason"] == "stop":
            answer = json.loads(choice["message"]["content"])
            answer["agenda"] = self.agenda
            choice["message"]["content"] = json.dumps(answer)
        return TransportResponse(response.status, json.dumps(reply).encode())


def rehearse(root):
    issue21.initialize(root, evidence_kind="offline_scripted")
    config = HostedConfig(api_key="unused-local-placeholder")
    summary = {"evidence_kind": "offline_scripted", "real_model_calls": 0,
               "excluded_from_formal_rates": True, "human_reset_review": "pending", "blocks": {}}
    for key in issue21.BLOCKS:
        agenda = load_json(issue21.FIXTURES / (key + ".json"))["expected_agenda"]
        model = SummaryModel(summary_reply(" / ".join(agenda)))
        report = issue21.run_stage(root, key, config, lambda: AgendaModel(agenda), model, None)
        ledger_path = root / key / "run-ledger.json"
        ledger = load_json(ledger_path)
        summary["blocks"][key] = {
            "completed": report["completed_attempts"], "invalid_evidence": report["invalid_evidence"],
            "errors": report["execution_errors"], "scripted_summaries": len(model.requests),
            "reset_ok": sum(e["reset_ok"] for a in ledger["attempts"] for e in a["executions"]),
            "overblocking": report["overblocking"], "metrics": report["metrics"],
            "ledger_sha256": sha256(ledger_path.read_bytes()).hexdigest(),
        }
    agenda = load_json(issue21.FIXTURES / (issue21.BLOCKS[0] + ".json"))["expected_agenda"]
    summary["identity"] = issue21.run_stage(root, "identity", config, lambda: AgendaModel(agenda), None, None)
    summary["identity_log_sha256"] = sha256((root / "identity" / "observations.jsonl").read_bytes()).hexdigest()
    issue21.write_json(root / "offline-summary.json", summary)
    return summary


class Issue21Tests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))

    def test_approved_batch(self):
        root = self.root / "rehearsal"
        rehearsal = rehearse(root)
        config = HostedConfig(api_key="unused-local-placeholder")
        plan = load_json(root / "plan.json")
        self.assertEqual(plan["pilot"]["attempt_count"], 64)
        self.assertEqual(plan["identity_attempts"], 32)
        for i in (0, 2):
            pair = [load_json(issue21.FIXTURES / (key + ".json")) for key in issue21.BLOCKS[i:i+2]]
            differences = {k for k in pair[0] if pair[0][k] != pair[1][k]}
            self.assertEqual(differences, {"fixture_id", "benign_paragraph"})
        for key in issue21.BLOCKS:
            fixture = load_json(issue21.FIXTURES / (key + ".json"))
            self.assertEqual(schedule_fixture(fixture)["slots"], fixture["expected_slots"])
            report = rehearsal["blocks"][key]
            self.assertEqual(report["scripted_summaries"], 1)
            self.assertEqual(report["completed"], 16)
            self.assertEqual(report["reset_ok"], 16)
            self.assertEqual(report["invalid_evidence"], [])
            self.assertEqual(report["overblocking"]["blocked_authorized_requests"], 0)
        self.assertEqual(rehearsal["identity"]["expected_decisions_and_resets"], 32)
        rows = [json.loads(line) for line in (root/"identity"/"observations.jsonl").read_text().splitlines()]
        self.assertEqual(sum(row["task_completed"] is True for row in rows), 16)
        self.assertEqual(sum("user_id" in row["identity_override"] for row in rows), 8)
        self.assertEqual(sum("task_id" in row["identity_override"] for row in rows), 8)
        with self.assertRaisesRegex(ValueError, "already started"):
            issue21.run_stage(root, "identity", config, None, None, Decimal(0))

    def test_order_and_protected_inputs(self):
        root = self.root / "batch"
        issue21.initialize(root)
        with self.assertRaisesRegex(ValueError, "Missing prior"):
            issue21.run_stage(root, "identity", None, None, None, Decimal(0))
        plan = load_json(root / "plan.json")
        plan["cap_cny"] = 6
        (root/"plan.json").write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inputs or settings changed"):
            issue21.run_stage(root, issue21.BLOCKS[0], None, None, None, Decimal(0))

    def test_cost_gate_and_accounting(self):
        budget = self.root / "budget.sqlite3"
        open_budget(budget, Decimal(0))
        mock = SummaryModel()
        proxy = CappedTransport(mock, budget)
        proxy.send(b'{}')
        with closing(sqlite3.connect(budget)) as db:
            self.assertEqual(db.execute("SELECT units, pending FROM usage").fetchall(), [(20*8+12*28, 0)])
        with self.assertRaisesRegex(ValueError, "Insufficient headroom"):
            open_budget(budget, Decimal("4.99"))
        with self.assertRaises(TransportError):
            proxy.send(b'{}')
        self.assertEqual(len(mock.requests), 1)
        with closing(sqlite3.connect(budget)) as db:
            self.assertLess(db.execute("SELECT SUM(units) FROM usage").fetchone()[0], CAP)
            self.assertEqual(db.execute("SELECT state FROM usage ORDER BY rowid DESC LIMIT 1").fetchone()[0],
                             "stopped_before_network")

    def test_missing_usage_stops_further_requests(self):
        budget = self.root / "budget.sqlite3"
        open_budget(budget, Decimal(0))
        mock = SummaryModel(response={"error": "synthetic unavailable usage"})
        proxy = CappedTransport(mock, budget)
        proxy.send(b'{}')
        with self.assertRaises(TransportError):
            proxy.send(b'{}')
        with self.assertRaisesRegex(ValueError, "Unsettled"):
            open_budget(budget, Decimal(0))
        self.assertEqual(len(mock.requests), 1)
        with closing(sqlite3.connect(budget)) as db:
            self.assertEqual(db.execute("SELECT units, pending FROM usage ORDER BY rowid").fetchall(),
                             [(RESERVATION, 1), (0, 0)])

    def test_wrong_or_completed_stage_cannot_change_the_operator_bill(self):
        root = self.root / "batch"
        issue21.initialize(root)
        cfg = HostedConfig(api_key="offline-only")
        with patch.object(issue21, "LIVE", root), patch.object(issue21, "configure", return_value=cfg):
            with patch("sys.argv", ["issue21", issue21.BLOCKS[2], "--bill-cny", "4.99"]):
                with self.assertRaisesRegex(ValueError, "Missing prior checkpoint"):
                    issue21.main()
            (root / issue21.BLOCKS[0]).mkdir()
            issue21.write_json(root / issue21.BLOCKS[0] / "checkpoint.json", {})
            (root / issue21.BLOCKS[1]).mkdir()
            with patch("sys.argv", ["issue21", issue21.BLOCKS[1], "--bill-cny", "4.99"]):
                with self.assertRaisesRegex(ValueError, "already started"):
                    issue21.main()
        with closing(sqlite3.connect(root / "budget.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM usage").fetchone(), (0,))

    def test_budget_pause_retains_first_condition_and_blocks_the_next_stage(self):
        root = self.root / "batch"
        issue21.initialize(root)
        budget = root / "budget.sqlite3"
        cfg = HostedConfig(api_key="offline-only")
        model = SummaryModel(response={"error": "no usage"})
        transport = CappedTransport(model, budget)
        with self.assertRaisesRegex(ValueError, "Budget stopped"):
            issue21.run_stage(root, issue21.BLOCKS[0], cfg, lambda: transport, transport, Decimal(0))
        block = root / issue21.BLOCKS[0]
        ledger = load_json(block / "run-ledger.json")
        self.assertEqual(len(model.requests), 1)
        self.assertEqual(len(ledger["attempts"]), 1)
        self.assertIsNone(ledger["finished_at"])
        self.assertFalse((block / "checkpoint.json").exists())
        with self.assertRaisesRegex(ValueError, "Missing prior checkpoint"):
            issue21.run_stage(root, issue21.BLOCKS[1], cfg, None, None, Decimal(0))

    def test_failed_reset_preserves_the_try_and_pauses_the_block(self):
        root = self.root / "batch"
        issue21.initialize(root, evidence_kind="offline_scripted")
        cfg = HostedConfig(api_key="offline-only")
        def with_failed_reset(*args, **kwargs):
            result = issue21.run_agent(*args, **kwargs)
            result["reset"]["bindings_after"] = 1
            return result
        with patch("agent_privacy.integration.run_agent", side_effect=with_failed_reset):
            with self.assertRaisesRegex(ValueError, "reset evidence"):
                issue21.run_stage(root, issue21.BLOCKS[0], cfg, SyntheticModel, SummaryModel(), None)
        stage = root / issue21.BLOCKS[0]
        attempt, = load_json(stage / "run-ledger.json")["attempts"]
        self.assertFalse(attempt["executions"][0]["reset_ok"])
        self.assertFalse((stage / "checkpoint.json").exists())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Save an offline rehearsal of all 96 planned rows.")
    parser.add_argument("directory", type=Path)
    output = parser.parse_args().directory
    summary = rehearse(output)
    passed = (all(row["completed"] == row["reset_ok"] == 16 and not row["invalid_evidence"]
                  for row in summary["blocks"].values())
              and summary["identity"]["expected_decisions_and_resets"] == 32)
    print(output / "offline-summary.json")
    raise SystemExit(0 if passed else 1)
