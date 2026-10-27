"""One recording boundary for every intended mock-cloud release."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .registry import ObjectRecord, ObjectRegistry


@dataclass(frozen=True)
class Authorization:
    active_task_id: str
    allowed: dict[str, dict[str, dict[str, tuple[str, ...]]]]


@dataclass(frozen=True)
class ReleaseRequest:
    task_id: str
    purpose: str
    recipient: str
    object_id: str
    fields: tuple[str, ...]
    reason: str = ""


class MockReceiver:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def receive(self, serialized: str) -> None:
        self.records.append(json.loads(serialized))


class ReleaseAdapter:
    def __init__(
        self,
        registry: ObjectRegistry,
        authorization: Authorization,
        configuration: str,
        receiver: MockReceiver,
    ) -> None:
        if configuration not in {"S0", "S3"}:
            raise ValueError("pilot only implements S0 and S3")
        self.registry = registry
        self.authorization = authorization
        self.configuration = configuration
        self.receiver = receiver
        self.proposals: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.outgoing_requests: list[dict[str, Any]] = []

    def _check_s3(self, request: ReleaseRequest, record: ObjectRecord) -> str | None:
        if request.task_id != self.authorization.active_task_id:
            return "request_task_mismatch"
        if record.task_id != self.authorization.active_task_id:
            return "object_task_mismatch"
        allowed_fields = (
            self.authorization.allowed.get(request.recipient, {})
            .get(request.purpose, {})
            .get(request.object_id)
        )
        if allowed_fields is None or not set(request.fields).issubset(allowed_fields):
            if record.confidentiality == "private":
                return "private_object_not_authorized"
            return "recipient_purpose_or_field_not_authorized"
        if record.confidentiality == "conditional" and not record.trusted_derivation:
            return "untrusted_derivation"
        return None

    def send(self, request: ReleaseRequest) -> dict[str, Any]:
        """Resolve a proposal through trusted records, then log actual send/receipt."""
        self.proposals.append(asdict(request))
        if request.recipient != "mock-cloud":
            return self._deny(request, "unsupported_pilot_recipient")
        try:
            record = self.registry.get(request.object_id)
        except KeyError:
            return self._deny(request, "unknown_object")
        if not request.fields or any(field not in record.fields for field in request.fields):
            return self._deny(request, "unknown_or_empty_field")
        reason = self._check_s3(request, record) if self.configuration == "S3" else None
        if reason is not None:
            return self._deny(request, reason)
        payload = {
            "task_id": request.task_id,
            "purpose": request.purpose,
            "object_id": record.object_id,
            "fields": {field: record.fields[field] for field in request.fields},
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.receiver.receive(serialized)
        self.outgoing_requests.append(
            {"recipient": request.recipient, "serialized": serialized, "bytes": len(serialized.encode("utf-8"))}
        )
        decision = {"allowed": True, "reason": "allowed", "request": asdict(request)}
        self.decisions.append(decision)
        return decision

    def _deny(self, request: ReleaseRequest, reason: str) -> dict[str, Any]:
        decision = {"allowed": False, "reason": reason, "request": asdict(request)}
        self.decisions.append(decision)
        return decision
