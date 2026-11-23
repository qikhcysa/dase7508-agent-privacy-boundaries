"""Offline checks for the Issue 23 formal budget boundary."""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from agent_privacy.issue23_budget import (
    CappedTransport,
    budget_status,
    check_budget_evidence,
    initialize_budget,
    open_budget,
)
from member_a.agent_core.transport import TransportError, TransportResponse


class Model:
    mode = "scripted"
    endpoint = "scripted://issue23-budget"

    def __init__(self, usage=True):
        self.usage = usage
        self.calls = 0

    def send(self, _body):
        self.calls += 1
        payload = {"choices": []}
        if self.usage:
            payload["usage"] = {"prompt_tokens": 100, "completion_tokens": 50}
        return TransportResponse(200, json.dumps(payload).encode())


class Issue23BudgetTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "budget.sqlite3"
        initialize_budget(self.path)

    def open(self, formal="0", daily="0", project="0", now=None):
        open_budget(
            self.path,
            formal_bill_cny=Decimal(formal),
            daily_bill_cny=Decimal(daily),
            project_bill_cny=Decimal(project),
            now=now,
        )

    def test_observed_usage_releases_reservation_and_counts_against_all_caps(self):
        self.open()
        model = Model()
        response = CappedTransport(model, self.path).send(b"{}")
        self.assertEqual(response.status, 200)
        self.assertEqual(model.calls, 1)
        check_budget_evidence(self.path)
        saved = budget_status(self.path)
        self.assertEqual(saved["formal_used_cny"], "0.00022")
        self.assertEqual(saved["daily_used_cny"], "0.00022")
        self.assertEqual(saved["project_used_cny"], "0.00022")
        # A lagging provider bill cannot erase token-derived usage at reconciliation.
        self.open()
        reconciled = budget_status(self.path)
        self.assertEqual(reconciled["formal_used_cny"], "0.00022")
        self.assertEqual(reconciled["daily_used_cny"], "0.00022")

    def test_protocol_boundary_examples(self):
        with self.assertRaisesRegex(ValueError, "current-day"):
            self.open(daily="19.20")
        self.open(daily="19.00")

        other = self.path.with_name("formal.sqlite3")
        initialize_budget(other)
        with self.assertRaisesRegex(ValueError, "formal-stage"):
            open_budget(other, formal_bill_cny=Decimal("119.20"),
                        daily_bill_cny=Decimal("0"), project_bill_cny=Decimal("0"))

        project = self.path.with_name("project.sqlite3")
        initialize_budget(project)
        with self.assertRaisesRegex(ValueError, "project"):
            open_budget(project, formal_bill_cny=Decimal("0"),
                        daily_bill_cny=Decimal("0"), project_bill_cny=Decimal("499.20"))

    def test_unknown_usage_retains_reservation_and_blocks_future_send(self):
        self.open()
        model = Model(usage=False)
        CappedTransport(model, self.path).send(b"first")
        with self.assertRaisesRegex(ValueError, "reserved"):
            check_budget_evidence(self.path)
        with self.assertRaisesRegex(TransportError, "issue23_budget_stopped_before_network"):
            CappedTransport(model, self.path).send(b"second")
        self.assertEqual(model.calls, 1)

    def test_daily_observation_may_reset_only_on_a_new_shanghai_day(self):
        first = datetime(2026, 11, 23, 4, tzinfo=timezone.utc)
        second = datetime(2026, 11, 24, 4, tzinfo=timezone.utc)
        self.open(formal="1", daily="1", project="1", now=first)
        with self.assertRaisesRegex(ValueError, "cannot decrease"):
            self.open(formal="1", daily="0", project="1", now=first)
        self.open(formal="1", daily="0", project="1", now=second)


if __name__ == "__main__":
    unittest.main()
