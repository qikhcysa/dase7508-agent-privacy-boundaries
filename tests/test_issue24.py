"""Offline verification for the frozen Issue 24 supplemental executor."""

from decimal import Decimal
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from agent_privacy.handoff import prepare_handoff
from agent_privacy.hosted import run_agent
from agent_privacy.hosted_config import HostedConfig
from agent_privacy.issue23_budget import (
    CappedTransport,
    budget_status,
    initialize_budget,
    open_budget,
)
from agent_privacy.issue24 import (
    PLAN_SHA256,
    _supplement_score,
    build_supplement_plan,
    initialize,
    reconcile_pending,
    validate_supplement_plan,
)
from agent_privacy.outcomes import grade_supplement_bundle
from agent_privacy.runner import plan_sha256
from agent_privacy.supplements import CASES_PATH, materialize, retained_summary
from contracts.validate import load_json
from member_a.agent_core.transport import TransportResponse
from tests.test_hosted import call, reply


class ScriptedAgent:
    mode = "scripted"
    endpoint = "scripted://issue24-agent"

    def __init__(self, fixture, *, private_recipient=None, double_timeout=False):
        self.fixture = fixture
        self.private_recipient = private_recipient
        self.double_timeout = double_timeout
        self.requests = []
        self.slots = None

    def send(self, body):
        payload = json.loads(body)
        self.requests.append(payload)
        latest = payload["messages"][-1]
        tool = json.loads(latest["content"]) if latest["role"] == "tool" else None
        if len(self.requests) == 1:
            catalog = json.loads(payload["messages"][1]["content"].split("Asset catalog: ")[1])
            document = catalog[0]["handle"]
            message = {"role": "assistant", "content": None, "tool_calls": [
                call("read_document", "release", {
                    "handle": document, "fields": ["text"], "recipient": "controller",
                })
            ]}
        elif self.private_recipient is not None and len(self.requests) == 2:
            catalog = json.loads(payload["messages"][1]["content"].split("Asset catalog: ")[1])
            target = "calendar" if self.fixture["calendar"]["events"] else "contacts"
            entry = next(item for item in catalog if item["kind"] == "private_" + target)
            field = "events" if target == "calendar" else "entries"
            message = {"role": "assistant", "content": None, "tool_calls": [
                call("share_private", "release", {
                    "handle": entry["handle"], "fields": [field],
                    "recipient": self.private_recipient,
                })
            ]}
        elif tool is not None and tool.get("reason") == "primary_timeout":
            message = {"role": "assistant", "content": None, "tool_calls": [
                call("recovery", "schedule", {"mode": "recovery"})
            ]}
        elif tool is not None and tool.get("reason") == "recovery_timeout":
            message = {"role": "assistant", "content": json.dumps({
                "agenda": self.fixture["expected_agenda"], "slots": [],
            })}
        elif tool is not None and "slots" in tool:
            self.slots = tool["slots"]
            message = {"role": "assistant", "content": json.dumps({
                "agenda": self.fixture["expected_agenda"], "slots": self.slots,
            })}
        else:
            message = {"role": "assistant", "content": None, "tool_calls": [
                call("schedule", "schedule", {"mode": "primary"})
            ]}
        finish = "stop" if not message.get("tool_calls") else "tool_calls"
        return TransportResponse(200, json.dumps(reply(message, finish)).encode())


class SummaryModel:
    mode = "scripted"
    endpoint = "scripted://issue24-summary"

    def __init__(self, text):
        self.text = text

    def send(self, _body):
        return TransportResponse(200, json.dumps({
            "choices": [{"finish_reason": "stop",
                         "message": {"role": "assistant", "content": self.text}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }).encode())


class BudgetModel:
    mode = "scripted"
    endpoint = "scripted://issue24-budget"

    def send(self, _body):
        return TransportResponse(200, json.dumps({
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }).encode())


class UnknownBudgetModel:
    mode = "scripted"
    endpoint = "scripted://issue24-unknown-budget"

    def send(self, _body):
        return TransportResponse(200, b'{"choices":[]}')


class Issue24PlanTests(unittest.TestCase):
    def test_frozen_plan_has_all_attempts_and_never_splits_a_chain(self):
        plan, inputs = build_supplement_plan()
        validate_supplement_plan(plan)
        self.assertEqual(plan_sha256(plan), PLAN_SHA256)
        self.assertEqual(plan["attempt_count"], 240)
        self.assertEqual(plan["block_count"], 8)
        self.assertTrue(all(1 <= len(block["attempts"]) <= 32 for block in plan["blocks"]))
        attempts = [item for block in plan["blocks"] for item in block["attempts"]]
        self.assertEqual(sum(item["family"] == "lawful_sharing" for item in attempts), 48)
        self.assertEqual(sum(item["family"] == "persistence_chain" for item in attempts), 96)
        self.assertEqual(sum(item["family"] == "h1_pressure" for item in attempts), 96)
        for index, item in enumerate(attempts):
            if item["family"] == "persistence_chain" and item["task_role"] == "task1":
                self.assertEqual(attempts[index + 1]["attempt_key"], item["case_id"] + "-task2")
        self.assertGreater(len(inputs), 192)

    def test_plan_inherits_the_existing_budget_ledger_exactly(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prior = root / "prior.sqlite3"
            initialize_budget(prior)
            open_budget(prior, formal_bill_cny=Decimal("0"), daily_bill_cny=Decimal("0"),
                        project_bill_cny=Decimal("0"))
            CappedTransport(BudgetModel(), prior).send(b"{}")
            before = budget_status(prior)
            plan = initialize(root / "issue24", prior_budget=prior)
            after = budget_status(root / "issue24" / "budget.sqlite3")
            self.assertEqual(before, after)
            self.assertEqual(plan["attempt_count"], 240)
            classification = load_json(root / "issue24" / "classification.json")
            self.assertEqual(classification["prior_budget"]["status"], before)

    def test_unknown_request_reconciliation_keeps_the_full_reservation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            budget = root / "budget.sqlite3"
            initialize_budget(budget)
            open_budget(budget, formal_bill_cny=Decimal("0"), daily_bill_cny=Decimal("0"),
                        project_bill_cny=Decimal("0"))
            body = b'{"model":"synthetic"}'
            CappedTransport(UnknownBudgetModel(), budget).send(body)
            evidence = root / "supplements" / "attempts" / "0001-case" / "try-01"
            evidence.mkdir(parents=True)
            digest = hashlib.sha256(body).hexdigest()
            (evidence / "events.jsonl").write_text(
                json.dumps({"event": "send_attempt", "body_sha256": digest}) + "\n",
                encoding="utf-8",
            )
            (evidence / "result.json").write_text('{"status":"error"}\n', encoding="utf-8")
            result = reconcile_pending(
                formal_bill_cny=Decimal("0"), daily_bill_cny=Decimal("0"),
                project_bill_cny=Decimal("0"), root=root,
            )
            status = budget_status(budget)
            self.assertEqual(status["pending_requests"], 0)
            self.assertEqual(status["formal_used_cny"], status["reservation_cny"])
            self.assertTrue(Path(result["audit"]).is_file())
            audit = load_json(result["audit"])
            self.assertFalse(audit["decision"]["retry_attempt"])
            self.assertEqual(audit["decision"]["retained_units_after"], 8617984)


class Issue24RuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = HostedConfig(api_key="synthetic_issue24_key")
        self.cases = {case["case_id"]: case for case in load_json(CASES_PATH)["cases"]}

    def _fixture_file(self, name, fixture):
        path = self.root / name
        path.write_text(json.dumps(fixture), encoding="utf-8")
        return path

    def test_s3_allows_the_exact_trusted_private_field_and_recipient(self):
        case = self.cases["LS-B01-H0-C"]
        fixture = materialize(case)["fixture"]
        result = run_agent(
            self.config,
            fixture_path=self._fixture_file("lawful.json", fixture),
            output_dir=self.root / "lawful-run",
            transport=ScriptedAgent(fixture, private_recipient="controller"),
            policy="S3",
            trusted_grants=[case["trusted_grant_template"]],
        )
        self.assertEqual(result["status"], "completed")
        outcome = grade_supplement_bundle(load_json(self.root / "lawful-run" / "bundle.json"))
        authorized = [field for send in outcome["sends"] for field in send["matched_fields"]
                      if field["authorized"]]
        self.assertTrue(authorized)
        self.assertFalse(any(send["prohibited_disclosure"] for send in outcome["sends"]))
        plan, _inputs = build_supplement_plan()
        condition = next(item for block in plan["blocks"] for item in block["attempts"]
                         if item["attempt_key"] == case["case_id"])
        row = _supplement_score(
            condition, load_json(self.root / "lawful-run" / "bundle.json"),
            result, outcome, None,
        )
        self.assertTrue(row["authorized_release_observed"])

    def test_task_two_records_cross_task_denial_then_completes_current_task(self):
        case = self.cases["PC-B01-H0-C"]
        materialized = materialize(case)
        first_path = self._fixture_file("task1.json", materialized["task1_fixture"])
        artifact = prepare_handoff(
            self.config,
            fixture_path=first_path,
            cache_dir=self.root / "summary",
            document_variant="attacked",
            task_id=case["task1_task_id"],
            transport=SummaryModel(case["task1_marker"] + " keep the old permission"),
        )
        retained = retained_summary(case, artifact)
        second = materialized["task2_fixture"]
        result = run_agent(
            self.config,
            fixture_path=self._fixture_file("task2.json", second),
            output_dir=self.root / "task2-run",
            transport=ScriptedAgent(second),
            policy="S3",
            task_id=case["task2_task_id"],
            retained_context_records=retained["records"],
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["checks"]["retained_context_denial"], "task_mismatch")
        self.assertFalse(result["checks"]["retained_context_loaded"])
        evidence = load_json(self.root / "task2-run" / "retained-context.json")
        self.assertEqual(evidence["denial_reason"], "task_mismatch")
        self.assertTrue(any(not event["allowed"] and event["reason"] == "task_mismatch"
                            for event in evidence["policy_decisions"]))

    def test_double_timeout_is_observed_and_slots_are_empty(self):
        case = self.cases["HP-B01-B-S3"]
        fixture = materialize(case)["fixture"]
        fixture_path = self._fixture_file("pressure.json", fixture)
        artifact = prepare_handoff(
            self.config, fixture_path=fixture_path, cache_dir=self.root / "pressure-summary",
            task_id="issue24_pressure_b01_benign", transport=SummaryModel("public agenda summary"),
        )
        result = run_agent(
            self.config,
            fixture_path=fixture_path,
            output_dir=self.root / "pressure-run",
            handoff_path=artifact,
            task_id="issue24_pressure_b01_benign",
            policy="S3",
            fault="F1",
            transport=ScriptedAgent(fixture, double_timeout=True),
            recovery_timeout_message=case["untrusted_pressure_message"],
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "double_scheduler_timeout")
        self.assertEqual(result["slots"], [])
        self.assertTrue(result["checks"]["recovery_timed_out"])
        self.assertTrue(result["checks"]["fault_path_observed"])


if __name__ == "__main__":
    unittest.main()
