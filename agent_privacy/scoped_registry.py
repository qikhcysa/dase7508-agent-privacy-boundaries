"""Immutable v1 records and explicit runtime context bindings.

Only trusted ingestion/orchestration calls this storage API. Model-facing tools
must not expose put, inspect_record, bind_context, or unbind_context. Scope
matching is a storage diagnostic, not a release policy or an authorization grant.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any
from uuid import uuid4

from contracts.validate import ContractError, validate

SCOPE_KEYS = ("user_id", "task_id", "trial_id", "session_id", "device_id")


class RegistryError(ValueError):
    """A stable reason code suitable for the runtime's audit log."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class RegistryScopeError(RegistryError):
    def __init__(self, status: dict):
        self.status = deepcopy(status)
        super().__init__(status["reason"])


def _json(value: Any) -> str:
    """Freeze finite JSON without coercing tuple values or non-string keys."""
    active: set[int] = set()
    pending = [(value, False)]
    while pending:
        item, leaving = pending.pop()
        if leaving:
            active.remove(id(item))
            continue
        if item is None or isinstance(item, (str, bool, int)):
            continue
        if isinstance(item, float):
            if not math.isfinite(item):
                raise RegistryError("invalid_json")
            continue
        if not isinstance(item, (dict, list)) or id(item) in active:
            raise RegistryError("invalid_json")
        active.add(id(item))
        pending.append((item, True))
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise RegistryError("invalid_json")
            pending.extend((child, False) for child in item.values())
        else:
            pending.extend((child, False) for child in item)
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        encoded.encode("utf-8")
        return encoded
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise RegistryError("invalid_json") from None


def _scope(scope: dict) -> tuple[dict, tuple[str, ...]]:
    frozen = json.loads(_json(scope))
    try:
        validate("scope", frozen)
    except ContractError:
        raise RegistryError("invalid_scope") from None
    return frozen, tuple(frozen[key] for key in SCOPE_KEYS)


def _handle(handle: str) -> str:
    if not isinstance(handle, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", handle) is None:
        raise RegistryError("invalid_handle")
    return handle


class ScopedRegistry:
    """SQLite-backed canonical records; labels never come from stored text.

    Handles are unique within one registry. put() is trusted-only and insert-only.
    get() checks an exact five-field context binding; inspect_record() is an
    intentionally unscoped trusted inspection API used by experiment policies.
    """

    def __init__(self, path: str | Path = ":memory:"):
        self._connection = sqlite3.connect(str(path))
        self._connection.execute("PRAGMA foreign_keys = ON")
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS v1_registry_objects ("
                "handle TEXT PRIMARY KEY NOT NULL, meta_json TEXT NOT NULL, value_json TEXT NOT NULL)"
            )
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS v1_registry_bindings ("
                "handle TEXT NOT NULL REFERENCES v1_registry_objects(handle), "
                "user_id TEXT NOT NULL, task_id TEXT NOT NULL, trial_id TEXT NOT NULL, "
                "session_id TEXT NOT NULL, device_id TEXT NOT NULL, "
                "binding_kind TEXT NOT NULL, binding_ref TEXT NOT NULL, "
                "PRIMARY KEY(handle,user_id,task_id,trial_id,session_id,device_id))"
            )

    def __enter__(self) -> ScopedRegistry:
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def put(self, value: dict, meta: dict, *, handle: str | None = None) -> str:
        """Trusted ingestion supplies labels separately from arbitrary value data."""
        handle = _handle("obj_" + uuid4().hex if handle is None else handle)
        meta_json, value_json = _json(meta), _json(value)
        metadata, frozen_value = json.loads(meta_json), json.loads(value_json)
        try:
            validate("object_metadata", metadata)
        except ContractError:
            raise RegistryError("invalid_metadata") from None
        try:
            validate("registry_object", {"handle": handle, "meta": metadata, "value": frozen_value})
        except ContractError:
            raise RegistryError("invalid_record") from None
        identity = tuple(metadata["original_scope"][key] for key in SCOPE_KEYS)
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            if self._connection.execute("SELECT 1 FROM v1_registry_objects WHERE handle=?", (handle,)).fetchone():
                raise RegistryError("duplicate_handle")
            for parent in metadata["derivation"]:
                if parent == handle:
                    raise RegistryError("self_derivation")
                if not self._connection.execute("SELECT 1 FROM v1_registry_objects WHERE handle=?", (parent,)).fetchone():
                    raise RegistryError("missing_derivation_parent")
            self._connection.execute("INSERT INTO v1_registry_objects VALUES (?,?,?)", (handle, meta_json, value_json))
            self._connection.execute("INSERT INTO v1_registry_bindings VALUES (?,?,?,?,?,?,?,?)",
                                     (handle, *identity, "original", "original"))
        return handle

    def put_record(self, record: dict) -> str:
        """Import a canonical record with an explicit handle and existing parents."""
        frozen = json.loads(_json(record))
        if not isinstance(frozen, dict) or set(frozen) != {"handle", "meta", "value"}:
            raise RegistryError("invalid_record")
        handle = frozen["handle"]
        if handle is None:
            raise RegistryError("invalid_handle")
        return self.put(frozen["value"], frozen["meta"], handle=handle)

    def inspect_record(self, handle: str) -> dict:
        """Trusted-only raw inspection; never expose this method as a model tool."""
        row = self._connection.execute("SELECT meta_json,value_json FROM v1_registry_objects WHERE handle=?",
                                       (_handle(handle),)).fetchone()
        if row is None:
            raise RegistryError("unknown_handle")
        return {"handle": handle, "meta": json.loads(row[0]), "value": json.loads(row[1])}

    def inspect_lineage(self, handle: str) -> list[dict]:
        """Inspect detached provenance only, without exposing parent values."""
        result, visited, active = [], set(), set()

        def visit(current: str) -> None:
            if current in active:
                raise RegistryError("cyclic_derivation")
            if current in visited:
                return
            row = self._connection.execute("SELECT meta_json FROM v1_registry_objects WHERE handle=?", (current,)).fetchone()
            if row is None:
                raise RegistryError("missing_derivation_parent")
            metadata = json.loads(row[0])
            result.append({"handle": current, "meta": metadata})
            active.add(current)
            for parent in metadata["derivation"]:
                visit(parent)
            active.remove(current)
            visited.add(current)
        visit(_handle(handle))
        return result

    def _scoped_lookup(self, handle: str, active_scope: dict) -> tuple[tuple, dict]:
        handle = _handle(handle)
        current, identity = _scope(active_scope)
        # One query gives one consistent view of the immutable row and binding.
        row = self._connection.execute(
            "SELECT o.meta_json,o.value_json,b.binding_kind,b.binding_ref FROM v1_registry_objects o "
            "LEFT JOIN v1_registry_bindings b ON o.handle=b.handle AND b.user_id=? AND b.task_id=? "
            "AND b.trial_id=? AND b.session_id=? AND b.device_id=? WHERE o.handle=?",
            (*identity, handle),
        ).fetchone()
        if row is None:
            raise RegistryError("unknown_handle")
        original = json.loads(row[0])["original_scope"]
        differences = [key for key in SCOPE_KEYS if current[key] != original[key]]
        principal_mismatch = next((key for key in ("user_id", "task_id") if key in differences), None)
        matches = row[2] is not None and principal_mismatch is None
        reason = ("original_context" if row[2] == "original" else "imported_context") if matches else (
            (principal_mismatch or differences[0]).removesuffix("_id") + "_mismatch" if differences else "context_not_bound")
        return row, {"matches": matches, "reason": reason, "differences": differences,
                     "original_scope": original, "active_scope": current,
                     "binding": {"kind": row[2], "reference": row[3]} if row[2] is not None else None}

    def check_scope(self, handle: str, active_scope: dict) -> dict:
        """Report context mismatch without applying confidentiality/release policy."""
        return self._scoped_lookup(handle, active_scope)[1]

    def get(self, handle: str, active_scope: dict) -> dict:
        row, status = self._scoped_lookup(handle, active_scope)
        if not status["matches"]:
            raise RegistryScopeError(status)
        return {"handle": handle, "meta": json.loads(row[0]), "value": json.loads(row[1])}

    def select_fields(self, handle: str, fields: list[str], active_scope: dict) -> dict:
        selection = json.loads(_json({"handle": handle, "fields": fields}))
        try:
            validate("selection", selection)
        except ContractError:
            raise RegistryError("invalid_selection") from None
        record = self.get(handle, active_scope)
        if not set(fields) <= record["value"].keys():
            raise RegistryError("unknown_field")
        record["value"] = {field: record["value"][field] for field in fields}
        # Every selected field retains the trusted object metadata. Labels found
        # inside value are ordinary data and are never merged into record.meta.
        return record

    def bind_context(self, handle: str, active_scope: dict, *, binding_ref: str) -> dict:
        """Trusted importer binds a same-user/task object without relabeling it.

        The caller must first verify the artifact and its intended use. This is
        not a model-facing tool or a grant to send the object's fields anywhere.
        """
        handle, binding_ref = _handle(handle), _handle(binding_ref)
        current, identity = _scope(active_scope)
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute("SELECT meta_json FROM v1_registry_objects WHERE handle=?", (handle,)).fetchone()
            if row is None:
                raise RegistryError("unknown_handle")
            original = json.loads(row[0])["original_scope"]
            for key in ("user_id", "task_id"):
                if original[key] != current[key]:
                    raise RegistryError(key.removesuffix("_id") + "_mismatch")
            existing = self._connection.execute(
                "SELECT binding_kind,binding_ref FROM v1_registry_bindings WHERE handle=? AND user_id=? "
                "AND task_id=? AND trial_id=? AND session_id=? AND device_id=?", (handle, *identity)).fetchone()
            if existing is None:
                self._connection.execute("INSERT INTO v1_registry_bindings VALUES (?,?,?,?,?,?,?,?)",
                                         (handle, *identity, "trusted_import", binding_ref))
            elif existing[0] != "original" and existing[1] != binding_ref:
                raise RegistryError("binding_reference_conflict")
        return self.check_scope(handle, current)

    def list_handles(self, active_scope: dict) -> list[str]:
        _, identity = _scope(active_scope)
        return [row[0] for row in self._connection.execute(
            "SELECT handle FROM v1_registry_bindings WHERE user_id=? AND task_id=? AND trial_id=? "
            "AND session_id=? AND device_id=? ORDER BY handle", identity)]

    def unbind_context(self, active_scope: dict) -> int:
        """Trusted teardown removes only this context's bindings; provenance stays."""
        _, identity = _scope(active_scope)
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM v1_registry_bindings WHERE user_id=? AND task_id=? AND trial_id=? "
                "AND session_id=? AND device_id=?", identity)
        return cursor.rowcount
