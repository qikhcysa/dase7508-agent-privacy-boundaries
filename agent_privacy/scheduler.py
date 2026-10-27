"""Deterministic slot calculation from synthetic local calendar data."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _interval(item: dict[str, Any]) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(item["start"])
    end = datetime.fromisoformat(item["end"])
    if start >= end:
        raise ValueError("slot start must precede end")
    return start, end


def feasible_slots(
    candidates: list[dict[str, str]], events: list[dict[str, str]], limit: int = 3
) -> list[dict[str, str]]:
    """Return up to `limit` candidate slots that do not overlap private events."""
    if limit < 1:
        raise ValueError("limit must be positive")
    busy = [_interval(event) for event in events]
    accepted: list[dict[str, str]] = []
    for candidate in candidates:
        start, end = _interval(candidate)
        if any(start < busy_end and busy_start < end for busy_start, busy_end in busy):
            continue
        accepted.append({"start": candidate["start"], "end": candidate["end"]})
        if len(accepted) == limit:
            break
    return accepted
