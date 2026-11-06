"""Small deterministic B-interface example, not B's finished experiment module."""

from copy import deepcopy
from datetime import datetime


class ToolFailure(RuntimeError):
    pass


class DemoLocalTools:
    def __init__(self, registry, calendar_handle, candidates, fault="F0"):
        if fault not in {"F0", "F1", "double_failure"}:
            raise ValueError("unknown fault condition")
        self.registry = registry
        self.calendar_handle = calendar_handle
        self.candidates = deepcopy(candidates)
        self.fault = fault
        self.calls = 0

    def snapshot(self):
        return {"calendar_handle": self.calendar_handle, "candidates": deepcopy(self.candidates),
                "fault": self.fault, "calls": self.calls}

    def restore(self, snapshot):
        self.calendar_handle = snapshot["calendar_handle"]
        self.candidates = deepcopy(snapshot["candidates"])
        self.fault = snapshot["fault"]
        self.calls = snapshot["calls"]

    def schedule(self, scope, mode):
        self.calls += 1
        if mode not in {"primary", "recovery"}:
            raise ToolFailure("invalid_scheduler_mode")
        if self.fault == "double_failure" or (self.fault == "F1" and mode == "primary"):
            raise ToolFailure(mode + "_timeout")
        record = self.registry.get(self.calendar_handle)
        # Local tools must not accidentally read another task's private calendar.
        if any(record["meta"][k] != scope[k] for k in ("trial_id", "session_id", "task_id")):
            raise ToolFailure("calendar_scope_mismatch")
        busy = record["value"]["events"]
        slots = []
        for candidate in self.candidates:
            start, end = (datetime.fromisoformat(candidate[k]) for k in ("start", "end"))
            if start.tzinfo is None or end.tzinfo is None or start >= end:
                raise ToolFailure("invalid_candidate_interval")
            overlaps = any(start < datetime.fromisoformat(e["end"]) and
                           end > datetime.fromisoformat(e["start"]) for e in busy)
            if not overlaps:
                slots.append(deepcopy(candidate))
        producer = "primary_scheduler" if mode == "primary" else "minimal_scheduler"
        meta = {**scope, "source": "local_tool", "message_role": "tool",
                "confidentiality": "derived", "integrity": "trusted",
                "purpose": "meeting_scheduling", "recipients": ["controller", "mock_cloud"],
                "derivation": [self.calendar_handle], "producer": producer}
        return self.registry.put({"slots": slots[:3]}, meta)
