"""Fixed object and field rules for the S2 release baseline."""

from collections.abc import Mapping
from types import MappingProxyType

from contracts.validate import validate


class StaticAllowlist:
    """Snapshot rules supplied by trusted configuration before a run."""

    def __init__(self, rules: Mapping[str, list[str] | tuple[str, ...]]):
        if not isinstance(rules, Mapping):
            raise ValueError("The static allowlist must map object handles to explicit fields.")
        allowed = {}
        for handle, fields in rules.items():
            if not isinstance(fields, (list, tuple)):
                raise ValueError("Allowlisted fields must be a list or tuple.")
            selection = {"handle": handle, "fields": list(fields)}
            validate("selection", selection)
            allowed[handle] = frozenset(selection["fields"])
        self._allowed = MappingProxyType(allowed)

    def decide(self, selections: list[dict]) -> tuple[bool, str]:
        """Check previously validated selections against exact handles and fields."""
        for selection in selections:
            fields = self._allowed.get(selection["handle"])
            if fields is None:
                return False, "s2_object_not_allowlisted"
            if not fields.issuperset(selection["fields"]):
                return False, "s2_field_not_allowlisted"
        return True, "s2_allowlisted"
