"""Three-cap accounting for the frozen Issue 23 formal core."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
import sqlite3
from zoneinfo import ZoneInfo

from member_a.agent_core.transport import TransportError


UNITS_PER_CNY = 10_000_000
DAILY_CAP = 20 * UNITS_PER_CNY
FORMAL_CAP = 120 * UNITS_PER_CNY
PROJECT_CAP = 500 * UNITS_PER_CNY
RESERVATION = 1_048_576 * 8 + 8192 * 28
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _units(value: Decimal, *, name: str, cap: int) -> int:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be a nonnegative finite CNY amount")
    units = int((value * UNITS_PER_CNY).to_integral_value(rounding="ROUND_CEILING"))
    if units > cap:
        raise ValueError(f"{name} exceeds its approved cap")
    return units


def _today(now: datetime | None = None) -> str:
    current = datetime.now(SHANGHAI) if now is None else now.astimezone(SHANGHAI)
    return current.date().isoformat()


def _schema(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS usage ("
        "units INTEGER NOT NULL, pending INTEGER NOT NULL, body_sha256 TEXT, "
        "state TEXT NOT NULL, shanghai_day TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS operator_snapshot ("
        "singleton INTEGER PRIMARY KEY CHECK (singleton = 1), "
        "formal_bill_units INTEGER NOT NULL, project_bill_units INTEGER NOT NULL, "
        "daily_bill_units INTEGER NOT NULL, shanghai_day TEXT NOT NULL, "
        "recorded_total_units INTEGER NOT NULL, recorded_daily_units INTEGER NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS bill_history AS SELECT * FROM operator_snapshot WHERE 0"
    )


def _accounted_usage(db, day, total, day_total):
    # Each reconciled bill supplies a floor, plus the local usage recorded since
    # that observation. A lagging bill cannot erase a previous floor.
    formal_offset, project_offset, daily_offset = db.execute(
        "SELECT MAX(formal_bill_units - recorded_total_units), "
        "MAX(project_bill_units - recorded_total_units), "
        "MAX(CASE WHEN shanghai_day = ? THEN daily_bill_units - recorded_daily_units END) "
        "FROM (SELECT * FROM operator_snapshot UNION ALL SELECT * FROM bill_history)",
        (day,),
    ).fetchone()
    if formal_offset is None:
        raise ValueError("Missing Issue 23 budget initialization")
    return (total + max(0, formal_offset), total + max(0, project_offset),
            day_total + max(0, daily_offset or 0))


def initialize_budget(path) -> None:
    day = _today()
    with closing(sqlite3.connect(path)) as db, db:
        _schema(db)
        if db.execute("SELECT COUNT(*) FROM operator_snapshot").fetchone()[0]:
            raise ValueError("Issue 23 budget ledger already exists")
        db.execute("INSERT INTO operator_snapshot VALUES (1, 0, 0, 0, ?, 0, 0)", (day,))


def check_budget_evidence(path) -> None:
    with closing(sqlite3.connect(path)) as db:
        _schema(db)
        blocked = db.execute(
            "SELECT state FROM usage WHERE pending = 1 OR state LIKE 'stopped_before_network:%' "
            "ORDER BY rowid LIMIT 1"
        ).fetchone()
    if blocked:
        raise ValueError(f"Budget stopped ({blocked[0]}). Reconcile retained evidence before continuing.")


def open_budget(path, *, formal_bill_cny: Decimal, daily_bill_cny: Decimal,
                project_bill_cny: Decimal, now: datetime | None = None) -> None:
    formal = _units(formal_bill_cny, name="Formal cumulative bill", cap=FORMAL_CAP)
    daily = _units(daily_bill_cny, name="Current-day bill", cap=DAILY_CAP)
    project = _units(project_bill_cny, name="Project cumulative bill", cap=PROJECT_CAP)
    day = _today(now)
    if formal + RESERVATION > FORMAL_CAP:
        raise ValueError("Insufficient formal-stage headroom for one request")
    if project + RESERVATION > PROJECT_CAP:
        raise ValueError("Insufficient project headroom for one request")
    if daily + RESERVATION > DAILY_CAP:
        raise ValueError("Insufficient current-day headroom for one request")
    with closing(sqlite3.connect(path)) as db, db:
        _schema(db)
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM usage WHERE pending = 1").fetchone()[0]:
            raise ValueError("Unsettled request: reconcile retained evidence before further sends")
        previous = db.execute(
            "SELECT formal_bill_units, project_bill_units, daily_bill_units, shanghai_day "
            "FROM operator_snapshot WHERE singleton = 1"
        ).fetchone()
        if previous is None:
            raise ValueError("Missing Issue 23 budget initialization")
        if formal < previous[0] or project < previous[1] or (day == previous[3] and daily < previous[2]):
            raise ValueError("Operator bill observations cannot decrease")
        total = db.execute("SELECT COALESCE(SUM(units), 0) FROM usage").fetchone()[0]
        day_total = db.execute(
            "SELECT COALESCE(SUM(units), 0) FROM usage WHERE shanghai_day = ?", (day,)
        ).fetchone()[0]
        db.execute("INSERT INTO bill_history SELECT * FROM operator_snapshot WHERE singleton=1")
        db.execute(
            "UPDATE operator_snapshot SET formal_bill_units = ?, project_bill_units = ?, "
            "daily_bill_units = ?, shanghai_day = ?, recorded_total_units = ?, "
            "recorded_daily_units = ? WHERE singleton = 1",
            (formal, project, daily, day, total, day_total),
        )
        formal_used, project_used, daily_used = _accounted_usage(db, day, total, day_total)
        if formal_used + RESERVATION > FORMAL_CAP:
            raise ValueError("Insufficient formal-stage headroom for one request")
        if project_used + RESERVATION > PROJECT_CAP:
            raise ValueError("Insufficient project headroom for one request")
        if daily_used + RESERVATION > DAILY_CAP:
            raise ValueError("Insufficient current-day headroom for one request")


def budget_status(path, *, now: datetime | None = None) -> dict:
    day = _today(now)
    with closing(sqlite3.connect(path)) as db:
        # Keep the status read consistent and leave archived ledger files untouched.
        db.execute("BEGIN")
        _schema(db)
        total = db.execute("SELECT COALESCE(SUM(units), 0) FROM usage").fetchone()[0]
        day_total = db.execute(
            "SELECT COALESCE(SUM(units), 0) FROM usage WHERE shanghai_day = ?", (day,)
        ).fetchone()[0]
        pending = db.execute("SELECT COUNT(*) FROM usage WHERE pending = 1").fetchone()[0]
        formal, project, daily = _accounted_usage(db, day, total, day_total)
    return {
        "shanghai_day": day,
        "formal_used_cny": str(Decimal(formal) / UNITS_PER_CNY),
        "daily_used_cny": str(Decimal(daily) / UNITS_PER_CNY),
        "project_used_cny": str(Decimal(project) / UNITS_PER_CNY),
        "pending_requests": pending,
        "reservation_cny": str(Decimal(RESERVATION) / UNITS_PER_CNY),
    }


class CappedTransport:
    def __init__(self, transport, path, *, now=None):
        self.transport = transport
        self.mode = transport.mode
        self.endpoint = transport.endpoint
        self.path = path
        self.now = now

    def send(self, body):
        digest = sha256(body).hexdigest()
        day = _today(self.now() if callable(self.now) else self.now)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM operator_snapshot WHERE singleton=1").fetchone() is None:
                raise TransportError("issue23_budget_not_initialized")
            total, pending = db.execute(
                "SELECT COALESCE(SUM(units), 0), COALESCE(SUM(pending), 0) FROM usage"
            ).fetchone()
            day_total = db.execute(
                "SELECT COALESCE(SUM(units), 0) FROM usage WHERE shanghai_day = ?", (day,)
            ).fetchone()[0]
            formal, project, daily = _accounted_usage(db, day, total, day_total)
            reason = None
            if pending:
                reason = "pending"
            elif daily + RESERVATION > DAILY_CAP:
                reason = "daily_cap"
            elif formal + RESERVATION > FORMAL_CAP:
                reason = "formal_cap"
            elif project + RESERVATION > PROJECT_CAP:
                reason = "project_cap"
            if reason is not None:
                db.execute(
                    "INSERT INTO usage VALUES (0, 0, ?, ?, ?)",
                    (digest, "stopped_before_network:" + reason, day),
                )
            else:
                request_id = db.execute(
                    "INSERT INTO usage VALUES (?, 1, ?, 'reserved', ?)",
                    (RESERVATION, digest, day),
                ).lastrowid
        if reason is not None:
            raise TransportError("issue23_budget_stopped_before_network")
        response = self.transport.send(body)
        try:
            usage = json.loads(response.body)["usage"]
            inputs, outputs = usage["prompt_tokens"], usage["completion_tokens"]
        except (ValueError, UnicodeError, KeyError, TypeError):
            return response
        if type(inputs) is int and type(outputs) is int and 0 <= inputs <= 1_048_576 and 0 <= outputs <= 8192:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute(
                    "UPDATE usage SET units = ?, pending = 0, state = 'observed_usage' WHERE rowid = ?",
                    (inputs * 8 + outputs * 28, request_id),
                )
        return response
