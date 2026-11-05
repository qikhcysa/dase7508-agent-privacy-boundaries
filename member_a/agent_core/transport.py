"""Explicit transports and append-only evidence for exact outbound bytes."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import math
from pathlib import Path
import threading
import time
from typing import Any, Protocol
from urllib.parse import urlsplit
import uuid


def _encode(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _byte_evidence(body: bytes, prefix: str) -> dict[str, Any]:
    return {
        f"{prefix}_base64": base64.b64encode(body).decode("ascii"),
        f"{prefix}_sha256": hashlib.sha256(body).hexdigest(),
        f"{prefix}_byte_count": len(body),
    }


@dataclass(frozen=True)
class TransportResponse:
    status: int
    body: bytes


class Transport(Protocol):
    mode: str
    endpoint: str

    def send(self, body: bytes) -> TransportResponse: ...

    def snapshot(self) -> dict[str, Any]: ...

    def restore(self, snapshot: dict[str, Any]) -> None: ...


def _validate_snapshot(snapshot: dict[str, Any], mode: str, endpoint: str) -> None:
    if not isinstance(snapshot, dict):
        raise ValueError("Transport snapshot must be a JSON object.")
    if snapshot.get("mode") != mode or snapshot.get("endpoint") != endpoint:
        raise ValueError("Transport snapshot mode or endpoint does not match.")


def _decode_snapshot_bytes(values: Any, field: str) -> list[bytes]:
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError(f"Snapshot {field} must be a list of base64 strings.")
    try:
        return [base64.b64decode(value, validate=True) for value in values]
    except ValueError:
        raise ValueError(f"Snapshot {field} contains invalid base64.") from None


class TransportError(RuntimeError):
    """No usable response was observed; remote delivery may be unknown."""


class ResponseError(RuntimeError):
    """The observed response was unsuccessful or not a JSON object."""

    def __init__(self, message: str, *, status: int, send_id: str):
        super().__init__(message)
        self.status = status
        self.send_id = send_id


class HttpTransport:
    """One direct JSON POST, without redirects, proxies, or automatic retries."""

    mode = "http"

    def __init__(self, endpoint: str, api_key: str = "", timeout: float = 20):
        if not isinstance(endpoint, str) or not endpoint:
            raise ValueError("An HTTP endpoint is required.")
        if any(ord(char) <= 32 or ord(char) == 127 for char in endpoint):
            raise ValueError("Endpoint must not contain whitespace or control characters.")
        if "?" in endpoint or "#" in endpoint:
            raise ValueError("Endpoint queries and fragments are forbidden.")
        try:
            parts = urlsplit(endpoint)
            host, port = parts.hostname, parts.port
        except ValueError:
            raise ValueError("Endpoint is not a valid URL.") from None
        if parts.scheme not in {"http", "https"} or not host:
            raise ValueError("Endpoint must be an absolute HTTPS URL.")
        if parts.username is not None or parts.password is not None:
            raise ValueError("Endpoint credentials are forbidden; use api_key.")
        if parts.scheme == "http":
            try:
                loopback = ipaddress.ip_address(host).is_loopback
            except ValueError:
                loopback = host.lower() == "localhost"
            if not loopback:
                raise ValueError("Unencrypted HTTP is allowed only for loopback addresses.")
        if not isinstance(api_key, str) or any(ord(c) < 32 or ord(c) == 127 for c in api_key):
            raise ValueError("API key must be a string without control characters.")
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            raise ValueError("Timeout must be a positive finite number.") from None
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be a positive finite number.")
        self.endpoint = endpoint
        self._scheme = parts.scheme
        self._host = host
        self._port = port
        self._path = parts.path or "/"
        self._api_key = api_key
        self._timeout = timeout

    def send(self, body: bytes) -> TransportResponse:
        if not isinstance(body, bytes):
            raise TypeError("Transport body must be bytes.")
        connection_type = (
            http.client.HTTPSConnection if self._scheme == "https" else http.client.HTTPConnection
        )
        connection = connection_type(self._host, self._port, timeout=self._timeout)
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            connection.request("POST", self._path, body=body, headers=headers)
            response = connection.getresponse()
            return TransportResponse(status=response.status, body=response.read())
        except Exception as exc:
            # Exception strings can contain request headers or credential values.
            raise TransportError(
                f"HTTP transport failed ({type(exc).__name__}); delivery is unknown."
            ) from None
        finally:
            connection.close()

    def snapshot(self) -> dict[str, Any]:
        # Requests are stateless; credentials never enter saved trial state.
        return {"mode": self.mode, "endpoint": self.endpoint}

    def restore(self, snapshot: dict[str, Any]) -> None:
        _validate_snapshot(snapshot, self.mode, self.endpoint)


class ScriptedTransport:
    """Replay local JSON objects; these are fixtures, never remote receipts."""

    mode = "scripted"
    endpoint = "scripted://controller"

    def __init__(self, responses: list[dict]):
        if not isinstance(responses, list) or any(not isinstance(r, dict) for r in responses):
            raise TypeError("Scripted responses must be a list of JSON objects.")
        self._responses = [_encode(response) for response in responses]
        self._script_sha256 = hashlib.sha256(b"[" + b",".join(self._responses) + b"]").hexdigest()
        self._index = 0
        self._lock = threading.Lock()
        self.requests: list[bytes] = []

    def send(self, body: bytes) -> TransportResponse:
        if not isinstance(body, bytes):
            raise TypeError("Transport body must be bytes.")
        with self._lock:
            if self._index >= len(self._responses):
                raise TransportError("Scripted response sequence is exhausted.")
            self.requests.append(body)
            response = self._responses[self._index]
            self._index += 1
        return TransportResponse(status=200, body=response)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": self.mode,
                "endpoint": self.endpoint,
                "script_sha256": self._script_sha256,
                "index": self._index,
                "requests_base64": [base64.b64encode(body).decode("ascii") for body in self.requests],
            }

    def restore(self, snapshot: dict[str, Any]) -> None:
        _validate_snapshot(snapshot, self.mode, self.endpoint)
        if snapshot.get("script_sha256") != self._script_sha256:
            raise ValueError("Snapshot response script does not match this transport.")
        index = snapshot.get("index")
        if type(index) is not int or not 0 <= index <= len(self._responses):
            raise ValueError("Snapshot script index is outside the response sequence.")
        requests = _decode_snapshot_bytes(snapshot.get("requests_base64"), "requests_base64")
        if len(requests) != index:
            raise ValueError("Snapshot request count does not match the script index.")
        with self._lock:
            self._index = index
            self.requests[:] = requests


class InProcessReceiver:
    """Receive exact bytes in this process; no network delivery occurs."""

    mode = "in_process_mock"
    endpoint = "mock://receiver"

    def __init__(self):
        self.receipts: list[bytes] = []
        self._lock = threading.Lock()

    def send(self, body: bytes) -> TransportResponse:
        if not isinstance(body, bytes):
            raise TypeError("Transport body must be bytes.")
        with self._lock:
            self.receipts.append(body)
        return TransportResponse(
            status=200,
            body=_encode({"accepted": True, "sha256": hashlib.sha256(body).hexdigest()}),
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": self.mode,
                "endpoint": self.endpoint,
                "receipts_base64": [base64.b64encode(body).decode("ascii") for body in self.receipts],
            }

    def restore(self, snapshot: dict[str, Any]) -> None:
        _validate_snapshot(snapshot, self.mode, self.endpoint)
        receipts = _decode_snapshot_bytes(snapshot.get("receipts_base64"), "receipts_base64")
        with self._lock:
            self.receipts[:] = receipts


_AUDIT_LOCKS: dict[Path, threading.Lock] = {}
_AUDIT_LOCKS_GUARD = threading.Lock()


class AuditLog:
    """Append JSONL records to the caller's exact path; never truncate it."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _AUDIT_LOCKS_GUARD:
            self._lock = _AUDIT_LOCKS.setdefault(self.path, threading.Lock())

    def append(self, event: str, **fields: Any) -> dict[str, Any]:
        if not isinstance(event, str) or not event:
            raise ValueError("Audit event must be a nonempty string.")
        if {"timestamp", "event_id", "event"}.intersection(fields):
            raise ValueError("Audit metadata fields are reserved.")
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event_id": uuid.uuid4().hex,
            "event": event,
            **fields,
        }
        encoded = _encode(record).decode("utf-8")
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded + "\n")
                stream.flush()
        return record


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-JSON numeric constant: {value}")


class AuditedSender:
    """Record bytes before an attempt and preserve observed response bytes."""

    def __init__(self, transport: Transport, audit: AuditLog):
        self.transport = transport
        self.audit = audit
        self.last_send_id: str | None = None

    def send(
        self, payload: dict, *, scope: dict, channel: str, configuration: str
    ) -> dict:
        if not isinstance(payload, dict) or not isinstance(scope, dict):
            raise TypeError("Payload and scope must be JSON objects.")
        if not isinstance(channel, str) or not isinstance(configuration, str):
            raise TypeError("Channel and configuration must be strings.")
        body = _encode(payload)
        # Snapshot metadata so concurrent caller mutations cannot change evidence.
        scope_snapshot = json.loads(_encode(scope))
        send_id = uuid.uuid4().hex
        common = {
            "send_id": send_id,
            "scope": scope_snapshot,
            "channel": channel,
            "configuration": configuration,
            "transport_mode": self.transport.mode,
            "endpoint": self.transport.endpoint,
        }
        self.audit.append(
            "send_attempt", **common, **_byte_evidence(body, "body"), delivery="attempted"
        )
        self.last_send_id = send_id
        started = time.perf_counter()
        try:
            response = self.transport.send(body)
        except Exception as exc:
            self.audit.append(
                "send_error",
                **common,
                delivery="delivery_unknown",
                error_type=type(exc).__name__,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
            )
            raise TransportError(
                f"Transport failed ({type(exc).__name__}); delivery is unknown; no retry was made."
            ) from None
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        parsed = None
        parse_error = None
        try:
            parsed = json.loads(response.body.decode("utf-8"), parse_constant=_reject_constant)
            if not isinstance(parsed, dict):
                raise ValueError("Response must be a JSON object.")
        except (UnicodeDecodeError, ValueError) as exc:
            parse_error = type(exc).__name__
        event, delivery = {
            "http": ("http_response", "http_response_observed"),
            "in_process_mock": ("mock_receipt", "mock_receipt_observed"),
            "scripted": ("scripted_response", "scripted_response_observed"),
        }.get(self.transport.mode, ("transport_response", "response_observed"))
        fields = {
            **common,
            **_byte_evidence(response.body, "response"),
            "status": response.status,
            "latency_ms": latency_ms,
            "delivery": delivery,
        }
        if isinstance(parsed, dict) and "usage" in parsed:
            fields["token_usage"] = parsed["usage"]
        if parse_error:
            fields["parse_error"] = parse_error
        self.audit.append(event, **fields)
        if not 200 <= response.status < 300:
            raise ResponseError(
                f"Response status {response.status}; no redirect or retry was followed.",
                status=response.status,
                send_id=send_id,
            )
        if parse_error:
            raise ResponseError(
                "Response is not a valid UTF-8 JSON object; original bytes are preserved in the audit log.",
                status=response.status,
                send_id=send_id,
            )
        return parsed
