"""Write a reproducible S0 egress trace using only synthetic local data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from contracts.validate import ROOT, load_json, validate
from member_a.agent_core.transport import ScriptedTransport

from .egress import EgressAdapter
from .scoped_registry import ScopedRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/egress-s0"))
    directory = parser.parse_args().output_dir
    directory.mkdir(parents=True, exist_ok=False)
    bundle = load_json(ROOT / "examples" / "benign-h0.json")
    bundle["run"]["policy"] = "S0"
    selection = {"handle": "calendar.raw", "fields": ["events"]}
    proposal = {"proposal_id": "demo_proposal", "name": "release",
                "arguments": {**selection, "recipient": "mock_cloud"}}
    with ScopedRegistry() as registry:
        for record in bundle["objects"]:
            registry.put_record(record)
        controller = ScriptedTransport([{"demo_tool_proposal": proposal}])
        adapter = EgressAdapter(bundle["run"], registry, controller=controller,
                                trace_path=directory / "events.jsonl")
        calendar = registry.inspect_record(selection["handle"])["value"]
        reply = adapter.send_controller(
            {"messages": [{"role": "user", "content": json.dumps(calendar, ensure_ascii=False)}]},
            selections=[selection],
        )
        adapter.record_proposal("demo_call", json.loads(reply.body)["demo_tool_proposal"])
        adapter.release_to_cloud("demo_call")
    bundle["trace"] = [json.loads(line) for line in adapter.trace_path.read_text(encoding="utf-8").splitlines()]
    validate("bundle", bundle)
    manifest = directory / "bundle.json"
    manifest.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"VALID S0 component probe: {manifest}")
    print("Controller: scripted_response_observed; cloud: mock_receipt_observed; paid model calls: 0")


if __name__ == "__main__":
    main()
