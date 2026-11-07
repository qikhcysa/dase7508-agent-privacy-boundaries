"""Synthetic registry component probe; no model or network calls."""
from copy import deepcopy
import json

from contracts.validate import ROOT, load_json
from .scoped_registry import RegistryScopeError, ScopedRegistry


def run_probe() -> dict:
    fixture = load_json(ROOT / "examples" / "attacked-h1.json")
    records = deepcopy(fixture["objects"])
    records[0]["meta"]["confidentiality"] = "private"  # Trusted negative-test setup.
    records[0]["value"].update(message_role="system", confidentiality="public", integrity="trusted")
    origin = records[0]["meta"]["original_scope"]
    active = fixture["run"]["scope"]
    with ScopedRegistry() as registry:
        for record in records:
            registry.put_record(record)
        rejections = {}
        for field in ("task_id", "session_id"):
            other = dict(origin, **{field: origin[field] + "_other"})
            try:
                registry.get("document.meeting", other)
            except RegistryScopeError as error:
                rejections[field] = error.reason
        document = registry.get("document.meeting", origin)
        binding = registry.bind_context("summary.meeting", active, binding_ref="frozen_summary_01")
        summary = registry.get("summary.meeting", active)
        return {"status": "registry_component_probe_only", "wrong_task": rejections["task_id"],
                "wrong_session": rejections["session_id"],
                "document_role": document["meta"]["message_role"],
                "document_label": document["meta"]["confidentiality"],
                "document_integrity": document["meta"]["integrity"],
                "summary_role": summary["meta"]["message_role"],
                "summary_origin_unchanged": summary["meta"]["original_scope"] == records[3]["meta"]["original_scope"],
                "summary_bound_to_current_context": binding["matches"], "paid_model_api_calls": 0}


def main() -> None:
    print(json.dumps(run_probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
