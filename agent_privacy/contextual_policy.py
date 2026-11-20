"""S3 authorization over trusted records and current runtime grants."""

from contracts.validate import ContractError, validate

from .scoped_registry import RegistryError


def has_trusted_summary_lineage(run, lineage):
    if run["handoff"] != "H1" or len(lineage) != 2:
        return False
    summary, parent = (item["meta"] for item in lineage)
    return (
        summary["producer"] == "handoff_summary"
        and summary["message_role"] == "assistant"
        and summary["integrity"] == "untrusted"
        and summary["original_scope"]["device_id"] == "desktop"
        and parent["source"] == "meeting_document"
        and parent["producer"] == "fixture_loader"
        and parent["integrity"] == "untrusted"
        and parent["message_role"] == "tool"
        and parent["original_scope"] == summary["original_scope"]
        and parent["purpose"] == summary["purpose"]
    )


def has_trusted_slots_lineage(run, record, lineage):
    if len(lineage) != 2:
        return False
    slots, calendar = (item["meta"] for item in lineage)
    producer = {"F0": "primary_scheduler", "F1": "minimal_scheduler"}[run["fault"]]
    value = record["value"]
    return (
        slots["source"] == "local_tool"
        and slots["producer"] == producer
        and slots["integrity"] == "trusted"
        and slots["message_role"] == "tool"
        and slots["original_scope"] == run["scope"]
        and calendar["source"] == "local_calendar"
        and calendar["producer"] == "fixture_loader"
        and calendar["integrity"] == "trusted"
        and calendar["confidentiality"] == "private"
        and calendar["original_scope"] == slots["original_scope"]
        and calendar["purpose"] == slots["purpose"]
        and set(value) == {"slots"}
        and isinstance(value["slots"], list)
        and len(value["slots"]) <= 3
        and all(isinstance(slot, dict) and set(slot) == {"start", "end"}
                and all(isinstance(boundary, str) for boundary in slot.values())
                for slot in value["slots"])
    )


class ContextualPolicy:
    """Check one active run; only the trusted orchestrator may update its grants."""

    def __init__(self, run, registry, authorization):
        validate("authorization", authorization)
        if authorization["scope"] != run["scope"]:
            raise ValueError("S3 authorization must match the active run scope.")
        self._run = run
        self._registry = registry
        self._authorization = authorization

    def denial(self, selections, recipient):
        if not selections:
            return "empty_selection"
        try:
            validate("authorization", self._authorization)
        except ContractError:
            return "invalid_runtime_authorization"
        scope = self._run["scope"]
        purpose = self._run["purpose"]
        if self._authorization["scope"] != scope:
            return "authorization_scope_mismatch"
        for selection in selections:
            handle, fields = selection["handle"], set(selection["fields"])
            try:
                binding = self._registry.check_scope(handle, scope)
                if not binding["matches"]:
                    return binding["reason"]
                record = self._registry.get(handle, scope)
                meta = record["meta"]
                if meta["purpose"] != purpose:
                    return "purpose_mismatch"
                if recipient not in meta["recipients"]:
                    return "recipient_not_permitted"
                if not fields <= record["value"].keys():
                    return "unknown_field"
                source = meta["source"]
                if source in {"meeting_document", "model_summary"}:
                    if handle not in self._authorization["context_handles"]:
                        return "context_not_authorized"
                    if source == "model_summary" and (
                        binding["binding"]["kind"] != "trusted_import"
                        or not has_trusted_summary_lineage(self._run, self._registry.inspect_lineage(handle))
                    ):
                        return "invalid_summary_lineage"
                if meta["confidentiality"] == "derived" and not has_trusted_slots_lineage(
                    self._run, record, self._registry.inspect_lineage(handle)
                ):
                    return "untrusted_derivation"
            except RegistryError as exc:
                return str(exc)

            granted_fields = {
                field
                for grant in self._authorization["grants"]
                if (grant["handle"], grant["purpose"], grant["recipient"]) == (handle, purpose, recipient)
                for field in grant["fields"]
            }
            if not fields <= granted_fields:
                return ("private_fields_not_authorized" if meta["confidentiality"] == "private"
                        else "fields_not_authorized")
        return None
