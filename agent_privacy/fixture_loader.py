"""Load synthetic experiment fixtures through the shared v1 contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

from contracts.validate import ContractError, load_json, validate


_CREDENTIAL_PATTERNS = (
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._~-]{20,}\b", re.IGNORECASE)),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    (
        "assigned secret",
        re.compile(
            r"\b(?:password|passwd|api[_-]?key|secret|access[_-]?token)\s*[:=]\s*[\"']?[^\s\"']{12,}",
            re.IGNORECASE,
        ),
    ),
)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _reject_possible_credentials(fixture: dict[str, Any]) -> None:
    for text in _strings(fixture):
        for label, pattern in _CREDENTIAL_PATTERNS:
            if pattern.search(text):
                raise ContractError(f"Fixture contains a possible {label}")


def load_fixture(path: str | Path) -> dict[str, Any]:
    """Return a parsed fixture only after contract and credential checks pass."""
    fixture = load_json(path)
    validate("fixture", fixture)
    _reject_possible_credentials(fixture)
    return fixture
