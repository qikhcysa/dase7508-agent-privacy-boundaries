"""Frozen S1 phone pattern and explicit payload content boundaries."""

from copy import deepcopy
import json
import re


RULE_VERSION = "s1_phone_v1"
PHONE_REPLACEMENT = "[PHONE_REDACTED]"
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?852[\x2d ]?)?\d{8}(?!\d)", re.ASCII)


def redact_value(value):
    """Copy JSON data and replace matching substrings in string values."""
    if isinstance(value, str):
        return PHONE_PATTERN.sub(PHONE_REPLACEMENT, value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    return deepcopy(value)


def _content(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return redact_value(value)
        if isinstance(parsed, (dict, list, str)):
            return json.dumps(redact_value(parsed), ensure_ascii=False, allow_nan=False)
        return redact_value(value)
    if isinstance(value, list):
        parts = deepcopy(value)
        for part in parts:
            if (not isinstance(part, dict) or part.get("type") != "text"
                    or not isinstance(part.get("text"), str) or set(part) != {"type", "text"}):
                raise ValueError("S1 supports text content parts only.")
            part["text"] = _content(part["text"])
        return parts
    raise ValueError("S1 requires text content, text parts or null.")


def redact_payload(payload, recipient, *, s1_message_content: dict[int, str] | None = None):
    """Redact data, using pre-redacted content only for trusted runtime messages."""
    result = deepcopy(payload)
    if recipient == "mock_cloud":
        result["fields"] = redact_value(result["fields"])
    elif recipient == "controller":
        runtime_content = s1_message_content or {}
        for index, message in enumerate(result["messages"]):
            if "content" in message:
                message["content"] = (runtime_content[index] if index in runtime_content
                                      else _content(message["content"]))
            for call in message.get("tool_calls", []):
                function = call.get("function", {})
                if function.get("name") == "save_memory":
                    try:
                        args = json.loads(function["arguments"])
                        if not isinstance(args, dict) or not isinstance(args.get("content"), str):
                            raise ValueError("S1 requires text memory content.")
                        args["content"] = redact_value(args["content"])
                        function["arguments"] = json.dumps(args, ensure_ascii=False, allow_nan=False)
                    except (KeyError, TypeError, ValueError):
                        raise ValueError("S1 requires valid save_memory text arguments.") from None
    else:
        raise ValueError("Unknown S1 recipient.")
    return result
