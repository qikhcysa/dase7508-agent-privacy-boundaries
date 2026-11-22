"""Issue 21 accounting for one operator's approved GLM text batch."""

from contextlib import closing
from decimal import Decimal
from hashlib import sha256
import json
import sqlite3

from member_a.agent_core.transport import TransportError


# Integer tenths of a microyuan. Standard text prices are CNY 0.8/2.8 per million.
UNITS_PER_CNY = 10_000_000
CAP = 5 * UNITS_PER_CNY
# Before actual usage is available, reserve a whole 1M context plus the 8192 output limit.
RESERVATION = 1_048_576 * 8 + 8192 * 28


def check_budget_evidence(path):
    with closing(sqlite3.connect(path)) as db:
        blocked = db.execute("SELECT state FROM usage WHERE pending = 1 OR state = 'stopped_before_network'"
                             " ORDER BY rowid LIMIT 1").fetchone()
    if blocked:
        raise ValueError(f"Budget stopped ({blocked[0]}). Reconcile the saved ledger before continuing.")


def open_budget(path, billed_cny):
    if not billed_cny.is_finite() or not Decimal(0) <= billed_cny <= Decimal(5):
        raise ValueError("Cumulative Issue 21 bill must be between 0 and 5 CNY")
    billed_units = int((billed_cny * UNITS_PER_CNY).to_integral_value(rounding="ROUND_CEILING"))
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS usage (units INTEGER NOT NULL, pending INTEGER NOT NULL,"
                   "body_sha256 TEXT, state TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM usage WHERE pending = 1").fetchone()[0]:
            raise ValueError("Unsettled request: reconcile the retained evidence before further sends")
        recorded = db.execute("SELECT COALESCE(SUM(units), 0) FROM usage").fetchone()[0]
        if billed_units > recorded:
            db.execute("INSERT INTO usage VALUES (?, 0, NULL, 'bill_adjustment')", (billed_units - recorded,))
    if max(billed_units, recorded) + RESERVATION > CAP:
        raise ValueError("Insufficient headroom for the next request. No new stage may start.")


class CappedTransport:
    def __init__(self, transport, path):
        self.transport = transport
        self.mode = transport.mode
        self.endpoint = transport.endpoint
        self.path = path

    def send(self, body):
        digest = sha256(body).hexdigest()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            spent, pending = db.execute(
                "SELECT COALESCE(SUM(units), 0), COALESCE(SUM(pending), 0) FROM usage"
            ).fetchone()
            stopped = pending or spent + RESERVATION > CAP
            if stopped:
                db.execute("INSERT INTO usage VALUES (0, 0, ?, 'stopped_before_network')", (digest,))
            else:
                request_id = db.execute("INSERT INTO usage VALUES (?, 1, ?, 'reserved')",
                                        (RESERVATION, digest)).lastrowid
        if stopped:
            raise TransportError("issue21_budget_stopped_before_network")
        # Missing usage, interruption or a transport error leaves the reservation in place.
        response = self.transport.send(body)
        try:
            usage = json.loads(response.body)["usage"]
            inputs, outputs = usage["prompt_tokens"], usage["completion_tokens"]
        except (ValueError, UnicodeError, KeyError, TypeError):
            return response
        if type(inputs) is int and type(outputs) is int and 0 <= inputs <= 1_048_576 and 0 <= outputs <= 8192:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("UPDATE usage SET units = ?, pending = 0, state = 'observed_usage' WHERE rowid = ?",
                           (inputs * 8 + outputs * 28, request_id))
        return response
