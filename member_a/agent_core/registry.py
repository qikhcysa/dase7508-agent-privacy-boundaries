"""Persistent JSON objects and isolated orchestration state.

The registry stores data and provenance without interpreting policy labels.
Snapshot restoration is intended for trusted experiment orchestration only.
"""

from __future__ import annotations

import json
import math
import sqlite3
import uuid
from pathlib import Path
from typing import Any


SCOPE_KEYS = ("trial_id", "session_id", "task_id", "device_id")
REQUIRED_META_KEYS = (
    "source", "message_role", "trial_id", "session_id", "task_id", "device_id",
    "confidentiality", "integrity", "purpose", "recipients", "derivation",
    "producer",
)
_META_LIST_KEYS = {"recipients", "derivation"}
_META_ENUMS = {
    "message_role": {"system", "user", "assistant", "tool"},
    "confidentiality": {"public", "private", "derived"},
    "integrity": {"trusted", "untrusted"},
}


def _validate_json(value: Any, label: str) -> None:
    """Reject non-JSON types, non-string keys, cycles and non-finite numbers."""
    active: set[int] = set()
    pending = [(value, False)]
    while pending:
        current, leaving = pending.pop()
        if leaving:
            active.remove(id(current))
            continue
        if current is None or isinstance(current, (str, bool, int)):
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                raise ValueError(f"{label} must contain only finite JSON numbers")
            continue
        if not isinstance(current, (dict, list)):
            raise ValueError(f"{label} contains a non-JSON value")
        if id(current) in active:
            raise ValueError(f"{label} contains a cycle")
        active.add(id(current))
        pending.append((current, True))
        if isinstance(current, dict):
            if any(not isinstance(key, str) for key in current):
                raise ValueError(f"{label} must have string object keys")
            pending.extend((item, False) for item in current.values())
        else:
            pending.extend((item, False) for item in current)


def _encode(value: Any, label: str) -> str:
    _validate_json(value, label)
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError(f"{label} cannot be encoded as JSON") from exc


def _handle(handle: Any) -> str:
    if not isinstance(handle, str) or not handle:
        raise ValueError("handle must be a non-empty string")
    return handle


def _meta(meta: Any) -> str:
    if not isinstance(meta, dict):
        raise ValueError("meta must be an object")
    missing = set(REQUIRED_META_KEYS) - meta.keys()
    if missing:
        raise ValueError(f"meta is missing required keys: {', '.join(sorted(missing))}")
    for key in REQUIRED_META_KEYS:
        value = meta[key]
        if key in _META_LIST_KEYS:
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError(f"meta.{key} must be a list of strings")
        elif not isinstance(value, str):
            raise ValueError(f"meta.{key} must be a string")
    for key, choices in _META_ENUMS.items():
        if meta[key] not in choices:
            raise ValueError(f"meta.{key} must be one of {', '.join(sorted(choices))}")
    return _encode(meta, "meta")


def _scope(scope: Any) -> tuple[str, str, str, str]:
    if not isinstance(scope, dict):
        raise ValueError("scope must be an object")
    if any(key not in scope or not isinstance(scope[key], str) for key in SCOPE_KEYS):
        raise ValueError("scope must include string trial_id, session_id, task_id and device_id")
    # Only these four identifiers define a state identity.
    return tuple(scope[key] for key in SCOPE_KEYS)


def _state(messages: Any, context_handles: Any, cache: Any) -> tuple[str, str, str]:
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    if not isinstance(context_handles, list) or any(
        not isinstance(handle, str) for handle in context_handles
    ):
        raise ValueError("context_handles must be a list of strings")
    if not isinstance(cache, dict):
        raise ValueError("cache must be an object")
    return (
        _encode(messages, "messages"),
        _encode(context_handles, "context_handles"),
        _encode(cache, "cache"),
    )


class Registry:
    """SQLite storage for immutable records and mutable scoped state.

    Invalid input and duplicate explicit handles raise ``ValueError``. Missing
    object reads/deletions raise ``KeyError``. Every returned JSON value is
    detached from storage. Context handles and provenance may refer to deleted
    or external objects; this layer does not apply reference or access policy.
    """

    def __init__(self, path: str | Path):
        self._connection = sqlite3.connect(str(path))
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS records ("
                "handle TEXT PRIMARY KEY NOT NULL, value_json TEXT NOT NULL, "
                "meta_json TEXT NOT NULL)"
            )
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS states ("
                "trial_id TEXT NOT NULL, session_id TEXT NOT NULL, "
                "task_id TEXT NOT NULL, device_id TEXT NOT NULL, "
                "messages_json TEXT NOT NULL, context_handles_json TEXT NOT NULL, "
                "cache_json TEXT NOT NULL, "
                "PRIMARY KEY (trial_id, session_id, task_id, device_id))"
            )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Registry:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def put(self, value: Any, meta: dict, handle: str | None = None) -> str:
        """Insert a new object; an existing handle can never be overwritten."""
        value_json, meta_json = _encode(value, "value"), _meta(meta)
        generated = handle is None
        while True:
            current_handle = "obj_" + uuid.uuid4().hex if generated else _handle(handle)
            try:
                with self._connection:
                    self._connection.execute(
                        "INSERT INTO records (handle, value_json, meta_json) VALUES (?, ?, ?)",
                        (current_handle, value_json, meta_json),
                    )
            except sqlite3.IntegrityError as exc:
                if generated:
                    continue
                raise ValueError(f"handle already exists: {current_handle}") from exc
            return current_handle

    def get(self, handle: str) -> dict:
        row = self._connection.execute(
            "SELECT value_json, meta_json FROM records WHERE handle = ?", (_handle(handle),)
        ).fetchone()
        if row is None:
            raise KeyError(handle)
        return {"handle": handle, "value": json.loads(row[0]), "meta": json.loads(row[1])}

    def list_handles(self) -> list[str]:
        return [row[0] for row in self._connection.execute("SELECT handle FROM records ORDER BY handle")]

    def delete(self, handle: str) -> None:
        with self._connection:
            cursor = self._connection.execute("DELETE FROM records WHERE handle = ?", (_handle(handle),))
            if cursor.rowcount == 0:
                raise KeyError(handle)

    def retire_value(self, handle: str) -> None:
        """Trusted harness only: erase content while retaining lineage metadata.

        This operation is deliberately separate from insert-only ``put`` and is
        not a model-facing tool. Derived provenance remains resolvable through
        the retained handle and original labels, with ``content_removed=True``.
        """
        handle = _handle(handle)
        with self._connection:
            # Acquire the write lock before reading metadata so concurrent
            # trusted changes cannot cause a stale read followed by an update.
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT meta_json FROM records WHERE handle = ?", (handle,)
            ).fetchone()
            if row is None:
                raise KeyError(handle)
            meta = json.loads(row[0])
            meta["content_removed"] = True
            self._connection.execute(
                "UPDATE records SET value_json = 'null', meta_json = ? WHERE handle = ?",
                (_meta(meta), handle),
            )

    def save_state(self, scope: dict, messages: list, context_handles: list, cache: dict) -> None:
        identity = _scope(scope)
        state = _state(messages, context_handles, cache)
        with self._connection:
            self._connection.execute(
                "INSERT INTO states (trial_id, session_id, task_id, device_id, "
                "messages_json, context_handles_json, cache_json) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (trial_id, session_id, task_id, device_id) DO UPDATE SET "
                "messages_json=excluded.messages_json, "
                "context_handles_json=excluded.context_handles_json, cache_json=excluded.cache_json",
                identity + state,
            )

    def load_state(self, scope: dict) -> dict:
        row = self._connection.execute(
            "SELECT messages_json, context_handles_json, cache_json FROM states "
            "WHERE trial_id=? AND session_id=? AND task_id=? AND device_id=?", _scope(scope)
        ).fetchone()
        if row is None:
            return {"messages": [], "context_handles": [], "cache": {}}
        return dict(zip(("messages", "context_handles", "cache"), map(json.loads, row)))

    def snapshot(self) -> dict:
        """Return a detached, deterministically ordered snapshot of all storage."""
        # A transaction provides one consistent view if another connection writes.
        with self._connection:
            self._connection.execute("BEGIN")
            records = [
                {"handle": row[0], "value": json.loads(row[1]), "meta": json.loads(row[2])}
                for row in self._connection.execute(
                    "SELECT handle, value_json, meta_json FROM records ORDER BY handle"
                )
            ]
            states = [
                {
                    "scope": dict(zip(SCOPE_KEYS, row[:4])),
                    "messages": json.loads(row[4]),
                    "context_handles": json.loads(row[5]),
                    "cache": json.loads(row[6]),
                }
                for row in self._connection.execute(
                    "SELECT trial_id, session_id, task_id, device_id, messages_json, "
                    "context_handles_json, cache_json FROM states "
                    "ORDER BY trial_id, session_id, task_id, device_id"
                )
            ]
        return {"version": 1, "records": records, "states": states}

    def restore(self, snapshot: dict) -> None:
        """Validate then atomically replace all records and all scoped state."""
        if not isinstance(snapshot, dict) or set(snapshot) != {"version", "records", "states"}:
            raise ValueError("snapshot must have version, records and states")
        if type(snapshot["version"]) is not int or snapshot["version"] != 1:
            raise ValueError("unsupported snapshot version")
        if not isinstance(snapshot["records"], list) or not isinstance(snapshot["states"], list):
            raise ValueError("snapshot records and states must be lists")
        records = []
        seen_handles = set()
        for record in snapshot["records"]:
            if not isinstance(record, dict) or set(record) != {"handle", "value", "meta"}:
                raise ValueError("snapshot record must have handle, value and meta")
            handle = _handle(record["handle"])
            if handle in seen_handles:
                raise ValueError(f"duplicate snapshot handle: {handle}")
            seen_handles.add(handle)
            records.append((handle, _encode(record["value"], "value"), _meta(record["meta"])))
        states = []
        seen_scopes = set()
        for state in snapshot["states"]:
            if not isinstance(state, dict) or set(state) != {"scope", "messages", "context_handles", "cache"}:
                raise ValueError("snapshot state must have scope, messages, context_handles and cache")
            identity = _scope(state["scope"])
            if identity in seen_scopes:
                raise ValueError("duplicate snapshot state scope")
            seen_scopes.add(identity)
            states.append(identity + _state(state["messages"], state["context_handles"], state["cache"]))
        with self._connection:
            self._connection.execute("DELETE FROM records")
            self._connection.execute("DELETE FROM states")
            self._connection.executemany(
                "INSERT INTO records (handle, value_json, meta_json) VALUES (?, ?, ?)", records
            )
            self._connection.executemany(
                "INSERT INTO states (trial_id, session_id, task_id, device_id, "
                "messages_json, context_handles_json, cache_json) VALUES (?, ?, ?, ?, ?, ?, ?)", states
            )

    def clear(self) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM records")
            self._connection.execute("DELETE FROM states")
