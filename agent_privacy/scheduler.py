"""Deterministic, local-only scheduling and recovery verification."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


MAX_SLOTS = 3
SCHEDULER_MODES = frozenset({"primary", "recovery"})


def _interval(item: dict[str, Any]) -> tuple[datetime, datetime]:
    try:
        start = datetime.fromisoformat(item["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(item["end"].replace("Z", "+00:00"))
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ValueError("invalid schedule interval") from None
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("schedule intervals must include a UTC offset")
    if start >= end:
        raise ValueError("slot start must precede end")
    return start, end


def feasible_slots(
    candidates: list[dict[str, str]],
    events: list[dict[str, str]],
    limit: int = MAX_SLOTS,
    meeting_minutes: int | None = None,
) -> list[dict[str, str]]:
    """Return the first 1--3 lawful candidates, or an empty list when none fit.

    Only the derived ``start`` and ``end`` fields are copied into the result.
    Candidate order is fixture order so repeated primary and recovery calls are
    deterministic.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_SLOTS:
        raise ValueError("limit must be between 1 and 3")
    if meeting_minutes is not None and (
        not isinstance(meeting_minutes, int)
        or isinstance(meeting_minutes, bool)
        or meeting_minutes < 1
    ):
        raise ValueError("meeting_minutes must be a positive integer")

    busy = [_interval(event) for event in events]
    accepted: list[dict[str, str]] = []
    for candidate in candidates:
        start, end = _interval(candidate)
        if meeting_minutes is not None and end - start != timedelta(minutes=meeting_minutes):
            continue
        if any(start < busy_end and busy_start < end for busy_start, busy_end in busy):
            continue
        accepted.append({"start": candidate["start"], "end": candidate["end"]})
        if len(accepted) == limit:
            break
    return accepted


def verify_schedule_result(
    result: dict[str, Any],
    candidates: list[dict[str, str]],
    events: list[dict[str, str]],
    meeting_minutes: int,
    limit: int = MAX_SLOTS,
) -> None:
    """Reject a result unless it is the exact minimal derived schedule output."""
    if not isinstance(result, dict) or set(result) != {"slots"}:
        raise ValueError("schedule result may contain only the slots field")
    slots = result["slots"]
    if not isinstance(slots, list):
        raise ValueError("schedule slots must be a list")
    if any(not isinstance(slot, dict) or set(slot) != {"start", "end"} for slot in slots):
        raise ValueError("schedule slots may contain only start and end")

    expected = feasible_slots(candidates, events, limit, meeting_minutes)
    if slots != expected:
        raise ValueError("schedule result does not match fixture constraints")


def schedule_fixture(
    fixture: dict[str, Any], mode: str = "primary", limit: int = MAX_SLOTS
) -> dict[str, list[dict[str, str]]]:
    """Run the trusted primary or common minimal recovery path locally.

    Fault selection is intentionally absent from this interface. A trusted
    runtime may choose ``recovery`` after a primary timeout, but a document or
    model cannot inject a fault switch through this function.
    """
    if mode not in SCHEDULER_MODES:
        raise ValueError("scheduler mode must be primary or recovery")

    candidates = fixture["candidate_slots"]
    events = fixture["calendar"]["events"]
    meeting_minutes = fixture["meeting_minutes"]
    result = {
        "slots": feasible_slots(candidates, events, limit, meeting_minutes),
    }
    verify_schedule_result(result, candidates, events, meeting_minutes, limit)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--mode", choices=sorted(SCHEDULER_MODES), default="primary")
    parser.add_argument("--limit", type=int, default=MAX_SLOTS)
    args = parser.parse_args(argv)

    from .fixture_loader import load_fixture

    result = schedule_fixture(load_fixture(args.fixture), args.mode, args.limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
