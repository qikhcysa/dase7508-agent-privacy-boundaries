"""Replaceable D/C integration adapter; reference rules are development fixtures.

This is not the team's final S0-S3 implementation or a security proof.
Only trusted orchestration may construct or replace these policies.
"""

from copy import deepcopy
import json
import re


class PolicyDenied(ValueError):
    pass


class ReferencePolicy:
    def __init__(self, configuration, registry, audit, static_fields=None, redactor=None):
        if configuration not in {"S0", "S1", "S2", "S3"}:
            raise ValueError("configuration must be S0, S1, S2 or S3")
        self.configuration = configuration
        self.registry = registry
        self.audit = audit
        self.static_fields = deepcopy(static_fields if static_fields is not None else {
            "meeting_document": None, "handoff_summary": None,
            "primary_scheduler": ["slots"], "minimal_scheduler": ["slots"],
        })
        self.redactor = redactor or self._example_redactor

    @staticmethod
    def _example_redactor(value):
        # Deliberately incomplete S1 comparator. C supplies the frozen final rules.
        if isinstance(value, str):
            return re.sub(r"(?<!\d)(?:\+?852[- ]?)?\d{8}(?!\d)", "[PHONE_REDACTED]", value)
        if isinstance(value, list):
            return [ReferencePolicy._example_redactor(v) for v in value]
        if isinstance(value, dict):
            return {k: ReferencePolicy._example_redactor(v) for k, v in value.items()}
        return value

    def snapshot(self):
        return {"configuration": self.configuration, "static_fields": deepcopy(self.static_fields)}

    def restore(self, snapshot):
        if snapshot["configuration"] != self.configuration:
            raise ValueError("reset cannot silently change experimental condition")
        self.static_fields = deepcopy(snapshot["static_fields"])

    def _scope_and_lineage(self, record, scope, seen=None):
        seen = set() if seen is None else seen
        handle, meta = record["handle"], record["meta"]
        if handle in seen:
            raise PolicyDenied("cyclic_derivation")
        seen = seen | {handle}
        if any(meta[k] != scope[k] for k in ("trial_id", "session_id", "task_id")):
            raise PolicyDenied("scope_mismatch")
        for parent in meta["derivation"]:
            try:
                origin = self.registry.get(parent)
            except KeyError as exc:
                raise PolicyDenied("missing_provenance") from exc
            self._scope_and_lineage(origin, scope, seen)

    def _log(self, operation, handle, scope, allowed, reason, **extra):
        self.audit.append("policy_decision", operation=operation, handle=handle,
                          scope=scope, configuration=self.configuration,
                          allowed=allowed, reason=reason, **extra)

    def check_load(self, record, scope, purpose):
        try:
            if self.configuration == "S3":
                self._scope_and_lineage(record, scope)
                if record["meta"]["purpose"] != purpose:
                    raise PolicyDenied("purpose_mismatch")
            self._log("load", record["handle"], scope, True, "load_allowed")
        except PolicyDenied as exc:
            self._log("load", record["handle"], scope, False, str(exc))
            raise

    def resolve(self, handle, scope, purpose, recipient, fields=None):
        record = self.registry.get(handle)
        meta, value = record["meta"], deepcopy(record["value"])
        try:
            if meta.get("content_removed"):
                raise PolicyDenied("original_content_removed")
            if fields is not None:
                if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
                    raise PolicyDenied("invalid_field_selection")
                if not isinstance(value, dict) or any(f not in value for f in fields):
                    raise PolicyDenied("unknown_field")
                value = {f: value[f] for f in fields}
            if self.configuration in {"S2", "S3"}:
                producer = meta["producer"]
                if producer not in self.static_fields:
                    raise PolicyDenied("object_not_allowlisted")
                allowed = self.static_fields[producer]
                if allowed is not None and (not isinstance(value, dict) or not set(value) <= set(allowed)):
                    raise PolicyDenied("field_not_allowlisted")
            if self.configuration == "S3":
                self._scope_and_lineage(record, scope)
                if meta["purpose"] != purpose:
                    raise PolicyDenied("purpose_mismatch")
                if recipient not in meta["recipients"]:
                    raise PolicyDenied("recipient_not_authorized")
                if meta["confidentiality"] == "derived":
                    if (meta["integrity"] != "trusted" or meta["producer"] not in {
                        "primary_scheduler", "minimal_scheduler"
                    } or not meta["derivation"]):
                        raise PolicyDenied("untrusted_declassification")
            if self.configuration == "S1":
                value = self.redactor(value)
            self._log("release", handle, scope, True, "release_allowed", recipient=recipient, fields=fields)
            return value
        except PolicyDenied as exc:
            self._log("release", handle, scope, False, str(exc), recipient=recipient, fields=fields)
            raise

    def prepare_payload(self, payload, scope, purpose, recipient, selections):
        # Re-check every previously materialized selection on EVERY send.
        for handle, fields in selections:
            self.resolve(handle, scope, purpose, recipient, fields)
        result = deepcopy(payload)
        if self.configuration == "S1":
            # Resolved values were redacted by resolve(). Do not mutate the API
            # schema, opaque handles or tool-call IDs when checking the envelope.
            if "value" in result:
                result["value"] = self.redactor(result["value"])
            for message in result.get("messages", []):
                if isinstance(message.get("content"), str):
                    message["content"] = self._redact_content(message["content"])
                for call in message.get("tool_calls", []):
                    function = call.get("function", {})
                    if function.get("name") == "save_memory":
                        args = json.loads(function["arguments"])
                        args["content"] = self.redactor(args["content"])
                        function["arguments"] = json.dumps(args, ensure_ascii=False)
        json.dumps(result, allow_nan=False)
        self.audit.append("payload_checked", scope=scope, configuration=self.configuration,
                          recipient=recipient, selection_count=len(selections))
        return result

    def _redact_content(self, content):
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            return self.redactor(content)

        def redact(value):
            if isinstance(value, dict):
                structural = {"handle", "asset_handles", "original_metadata", "source_metadata",
                              "tool_call_id", "send_id", "scope", "fields", "loaded_message_role"}
                return {k: deepcopy(v) if k in structural else redact(v) for k, v in value.items()}
            if isinstance(value, list):
                return [redact(v) for v in value]
            return self.redactor(value)

        return json.dumps(redact(parsed), ensure_ascii=False)
