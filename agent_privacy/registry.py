"""Local object registry. Model/document text cannot change these records."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ObjectRecord:
    object_id: str
    task_id: str
    source: str
    confidentiality: str
    trusted_derivation: bool
    fields: dict[str, Any]


class ObjectRegistry:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.connection = sqlite3.connect(str(path))
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS objects (
                object_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                source TEXT NOT NULL,
                confidentiality TEXT NOT NULL,
                trusted_derivation INTEGER NOT NULL,
                fields_json TEXT NOT NULL
            )"""
        )

    def add(self, record: ObjectRecord) -> None:
        if record.confidentiality not in {"public", "conditional", "private"}:
            raise ValueError("invalid confidentiality label")
        with self.connection:
            self.connection.execute(
                "INSERT INTO objects VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.object_id,
                    record.task_id,
                    record.source,
                    record.confidentiality,
                    int(record.trusted_derivation),
                    json.dumps(record.fields, sort_keys=True),
                ),
            )

    def get(self, object_id: str) -> ObjectRecord:
        row = self.connection.execute(
            "SELECT object_id, task_id, source, confidentiality, trusted_derivation, fields_json "
            "FROM objects WHERE object_id = ?", (object_id,)
        ).fetchone()
        if row is None:
            raise KeyError(object_id)
        return ObjectRecord(row[0], row[1], row[2], row[3], bool(row[4]), json.loads(row[5]))

    def close(self) -> None:
        self.connection.close()
