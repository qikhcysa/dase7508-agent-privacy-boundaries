import copy
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent_core.registry import Registry


def metadata(**overrides):
    result = {
        "source": "fixture", "message_role": "tool", "trial_id": "trial-1",
        "session_id": "session-1", "task_id": "task-1", "device_id": "device-1",
        "confidentiality": "private", "integrity": "untrusted", "purpose": "test",
        "recipients": ["owner"], "derivation": [], "producer": "test-registry",
    }
    result.update(overrides)
    return result


def scope(**overrides):
    result = {key: metadata()[key] for key in ("trial_id", "session_id", "task_id", "device_id")}
    result.update(overrides)
    return result


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "registry.sqlite3"
        self.registry = Registry(self.path)
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.registry.close)

    def test_records_and_state_survive_restart(self):
        handle = self.registry.put({"text": "夏张宁", "items": [1, None]}, metadata())
        self.assertTrue(handle.startswith("obj_"))
        self.registry.save_state(scope(), [{"role": "user", "content": "hello"}], [handle], {"n": 1})
        before = self.registry.snapshot()
        self.registry.close()
        with Registry(self.path) as reopened:
            self.assertEqual(before, reopened.snapshot())
        with self.assertRaises(sqlite3.ProgrammingError):
            reopened.list_handles()

    def test_duplicate_handle_does_not_overwrite(self):
        self.registry.put("original", metadata(), "fixed")
        with self.assertRaises(ValueError):
            self.registry.put("replacement", metadata(source="other"), "fixed")
        self.assertEqual(self.registry.get("fixed")["value"], "original")
        self.assertEqual(self.registry.list_handles(), ["fixed"])

    def test_returned_and_input_objects_are_detached(self):
        value, meta = {"items": [1]}, metadata(trace_ids=["trace-1"])
        handle = self.registry.put(value, meta)
        value["items"].append(2)
        meta["trace_ids"].append("trace-2")
        record = self.registry.get(handle)
        record["value"]["items"].append(3)
        record["meta"]["trace_ids"].append("trace-3")
        self.assertEqual(self.registry.get(handle)["value"], {"items": [1]})
        self.assertEqual(self.registry.get(handle)["meta"]["trace_ids"], ["trace-1"])
        messages, handles, cache = [{"content": ["x"]}], [handle], {"items": [1]}
        self.registry.save_state(scope(), messages, handles, cache)
        messages[0]["content"].append("changed")
        handles.clear()
        cache["items"].clear()
        loaded = self.registry.load_state(scope())
        loaded["messages"].clear()
        loaded["cache"]["items"].append(2)
        self.assertEqual(self.registry.load_state(scope()), {
            "messages": [{"content": ["x"]}], "context_handles": [handle], "cache": {"items": [1]},
        })
        snap = self.registry.snapshot()
        snap["records"][0]["value"]["items"].clear()
        self.assertEqual(self.registry.get(handle)["value"], {"items": [1]})

    def test_metadata_validation_and_extra_fields(self):
        for key in metadata():
            with self.subTest(missing=key):
                invalid = metadata()
                del invalid[key]
                with self.assertRaises(ValueError):
                    self.registry.put(None, invalid)
        for key, bad in (("source", 1), ("recipients", "owner"), ("derivation", [1]),
                         ("message_role", "developer"), ("integrity", "safe"),
                         ("confidentiality", "secret"), ("producer", None)):
            with self.subTest(key=key, value=bad):
                with self.assertRaises(ValueError):
                    self.registry.put(None, metadata(**{key: bad}))
        handle = self.registry.put(None, metadata(generated_by="summary", trace_ids=["a"], extra={"n": 1}))
        self.assertEqual(self.registry.get(handle)["meta"]["extra"], {"n": 1})

    def test_non_json_values_rejected(self):
        cyclic = []
        cyclic.append(cyclic)
        for value in ((1, 2), {1: "bad-key"}, {1, 2}, float("nan"), float("inf"), cyclic):
            with self.subTest(value_type=type(value)):
                with self.assertRaises(ValueError):
                    self.registry.put(value, metadata())
        self.assertEqual(self.registry.list_handles(), [])

    def test_state_isolation_for_every_scope_component(self):
        self.registry.save_state(scope(), ["base"], ["h"], {"base": True})
        for key in scope():
            alternate = scope(**{key: "alternate"})
            with self.subTest(key=key):
                self.assertEqual(self.registry.load_state(alternate), {
                    "messages": [], "context_handles": [], "cache": {},
                })
                self.registry.save_state(alternate, [key], [], {})
        self.assertEqual(self.registry.load_state(scope())["messages"], ["base"])
        for key in scope():
            self.assertEqual(self.registry.load_state(scope(**{key: "alternate"}))["messages"], [key])
        self.registry.save_state(scope(), ["updated"], [], {})
        self.assertEqual(self.registry.load_state(scope())["messages"], ["updated"])

    def test_state_validation_preserves_existing_state(self):
        self.registry.save_state(scope(), ["before"], [], {})
        for identity, messages, handles, cache in (
            ({}, [], [], {}), (scope(task_id=None), [], [], {}),
            (scope(), {}, [], {}), (scope(), [], [1], {}), (scope(), [], [], []),
            (scope(), [float("nan")], [], {}),
        ):
            with self.subTest(identity=identity, messages=messages, handles=handles, cache=cache):
                with self.assertRaises(ValueError):
                    self.registry.save_state(identity, messages, handles, cache)
        self.assertEqual(self.registry.load_state(scope())["messages"], ["before"])

    def test_delete_preserves_provenance_and_missing_raises(self):
        parent = self.registry.put("source", metadata(), "parent")
        child = self.registry.put("derived", metadata(confidentiality="derived", derivation=[parent]), "child")
        self.registry.save_state(scope(), [], [parent, child], {})
        self.registry.delete(parent)
        self.assertEqual(self.registry.get(child)["meta"]["derivation"], [parent])
        self.assertEqual(self.registry.load_state(scope())["context_handles"], [parent, child])
        for operation in (self.registry.get, self.registry.delete):
            with self.assertRaises(KeyError):
                operation(parent)

    def test_retire_value_erases_text_retains_lineage_and_survives_restart(self):
        original_meta = metadata(trace_ids=["trace-1"], generated_by="source-tool")
        source = self.registry.put({"content": "original sensitive text"}, original_meta, "source")
        child = self.registry.put("derived text", metadata(derivation=[source]), "child")
        self.registry.retire_value(source)
        expected_meta = dict(original_meta, content_removed=True)
        expected = {"handle": source, "value": None, "meta": expected_meta}
        self.assertEqual(self.registry.get(source), expected)
        self.assertEqual(self.registry.get(child)["meta"]["derivation"], [source])
        self.assertNotIn("original sensitive text", str(self.registry.snapshot()))
        self.assertIn(expected, self.registry.snapshot()["records"])
        self.registry.retire_value(source)
        self.assertEqual(self.registry.get(source), expected)
        self.registry.close()
        with Registry(self.path) as reopened:
            self.assertEqual(reopened.get(source), expected)
            with self.assertRaises(KeyError):
                reopened.retire_value("missing")

    def test_restore_database_failure_rolls_back_deletions(self):
        self.registry.put("before", metadata(), "before")
        self.registry.save_state(scope(), ["before"], [], {})
        baseline = self.registry.snapshot()
        incoming = {
            "version": 1,
            "records": [{"handle": "rejected", "value": "after", "meta": metadata()}],
            "states": [],
        }
        with closing(sqlite3.connect(self.path)) as external:
            external.execute(
                "CREATE TRIGGER reject_restore BEFORE INSERT ON records "
                "WHEN NEW.handle = 'rejected' BEGIN SELECT RAISE(ABORT, 'test failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.registry.restore(incoming)
        self.assertEqual(self.registry.snapshot(), baseline)

    def test_snapshot_restore_is_identical_and_resets_all_trials(self):
        self.registry.put("z-value", metadata(), "z")
        self.registry.put("a-value", metadata(), "a")
        self.registry.save_state(scope(trial_id="z"), ["z"], [], {})
        self.registry.save_state(scope(trial_id="a"), ["a"], ["a"], {"found": True})
        baseline = self.registry.snapshot()
        self.assertEqual([record["handle"] for record in baseline["records"]], ["a", "z"])
        self.assertEqual([state["scope"]["trial_id"] for state in baseline["states"]], ["a", "z"])
        self.registry.put("contamination", metadata(), "other-trial-object")
        self.registry.save_state(scope(trial_id="other-trial"), ["contamination"], [], {})
        self.registry.restore(baseline)
        self.assertEqual(self.registry.snapshot(), baseline)
        self.assertEqual(self.registry.load_state(scope(trial_id="other-trial"))["messages"], [])
        self.registry.restore(baseline)
        self.assertEqual(self.registry.snapshot(), baseline)
        self.registry.clear()
        self.assertEqual(self.registry.snapshot(), {"version": 1, "records": [], "states": []})
        self.registry.restore(baseline)
        self.assertEqual(self.registry.snapshot(), baseline)

    def test_invalid_restore_leaves_everything_unchanged(self):
        self.registry.put("original", metadata(), "original")
        self.registry.save_state(scope(), ["original"], ["original"], {"original": True})
        baseline = self.registry.snapshot()
        invalids = []
        for version in (True, 2, "1"):
            invalids.append(dict(baseline, version=version))
        bad_record = copy.deepcopy(baseline)
        bad_record["records"].append({"handle": "new", "value": "new", "meta": {}})
        invalids.append(bad_record)
        duplicate_record = copy.deepcopy(baseline)
        duplicate_record["records"] *= 2
        invalids.append(duplicate_record)
        bad_state = copy.deepcopy(baseline)
        bad_state["states"].append({"scope": scope(task_id="new"), "messages": {}, "context_handles": [], "cache": {}})
        invalids.append(bad_state)
        duplicate_state = copy.deepcopy(baseline)
        duplicate_state["states"] *= 2
        invalids.append(duplicate_state)
        invalids.extend(({}, dict(baseline, states={}), dict(baseline, records=[{}])))
        for invalid in invalids:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.registry.restore(invalid)
                self.assertEqual(self.registry.snapshot(), baseline)


if __name__ == "__main__":
    unittest.main()
