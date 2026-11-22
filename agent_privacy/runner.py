"""Reproducible core-matrix planning and execution for issue 19.

The runner owns ordering, evidence directories, retry records and reset checks.
It deliberately does not implement a policy or model loop; issue 20 supplies an
integrated executor that accepts one planned condition at a time.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any, Callable, Iterable

from contracts.validate import ContractError, load_json, validate

from .evaluation_metrics import trace_metrics
from .fixture_loader import load_fixture


ROOT = Path(__file__).resolve().parents[1]
POLICIES = ("S0", "S1", "S2", "S3")
HANDOFFS = ("H0", "H1")
FAULTS = ("F0", "F1")
DOCUMENT_VARIANTS = ("benign", "attacked")
PLAN_VERSION = "issue19-core-plan-v1"
LEDGER_VERSION = "issue19-run-ledger-v1"


class RunnerError(ValueError):
    """A stable runner error that does not include provider response text."""


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_ledger(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    _write_json(temporary, value)
    temporary.replace(path)


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _resolve_path(path: str | Path) -> Path:
    value = Path(path)
    return value.resolve() if value.is_absolute() else (ROOT / value).resolve()


def _condition_id(fixture_id: str, repetition: int, document_variant: str,
                  policy: str, handoff: str, fault: str) -> str:
    return "-".join((fixture_id, "r" + str(repetition), document_variant, policy, handoff, fault))


def _order_key(seed: str, block_id: str, condition: dict[str, Any]) -> str:
    material = {"seed": seed, "block_id": block_id, "condition": condition}
    return _sha256_bytes(_json_bytes(material))


def build_core_plan(
    fixture_paths: Iterable[str | Path] | None = None,
    *,
    repetitions: int = 3,
    seed: str | int = "dase7508-core-v1",
    policies: Iterable[str] = POLICIES,
    handoffs: Iterable[str] = HANDOFFS,
    faults: Iterable[str] = FAULTS,
    document_variants: Iterable[str] = DOCUMENT_VARIANTS,
) -> dict[str, Any]:
    """Build a portable plan with deterministic pseudo-random order per block.

    A block is one fixture and one repetition. Every S/H/F/document condition
    receives a hash-derived ordering key, avoiding Python RNG version drift.
    """
    if type(repetitions) is not int or repetitions < 1:
        raise RunnerError("repetitions_must_be_positive")
    seed = str(seed)
    dimensions = {
        "policies": tuple(policies),
        "handoffs": tuple(handoffs),
        "faults": tuple(faults),
        "document_variants": tuple(document_variants),
    }
    expected = {
        "policies": set(POLICIES),
        "handoffs": set(HANDOFFS),
        "faults": set(FAULTS),
        "document_variants": set(DOCUMENT_VARIANTS),
    }
    for name, values in dimensions.items():
        if not values or len(values) != len(set(values)) or not set(values) <= expected[name]:
            raise RunnerError("invalid_" + name)

    if fixture_paths is None:
        fixture_paths = sorted((ROOT / "fixtures" / "benign").glob("B*.json"))
    fixture_records = []
    seen = set()
    for supplied in fixture_paths:
        path = _resolve_path(supplied)
        fixture = load_fixture(path)
        fixture_id = fixture["fixture_id"]
        if fixture_id in seen:
            raise RunnerError("duplicate_fixture_id")
        seen.add(fixture_id)
        fixture_records.append({
            "fixture_id": fixture_id,
            "path": _portable_path(path),
            "sha256": _sha256_bytes(path.read_bytes()),
        })
    fixture_records.sort(key=lambda item: item["fixture_id"])
    if not fixture_records:
        raise RunnerError("no_fixtures")

    blocks = []
    for fixture_record in fixture_records:
        for repetition in range(1, repetitions + 1):
            block_id = f"{fixture_record['fixture_id']}-r{repetition}"
            attempts = []
            for variant, policy, handoff, fault in itertools.product(
                dimensions["document_variants"], dimensions["policies"],
                dimensions["handoffs"], dimensions["faults"]
            ):
                condition = {
                    "fixture_id": fixture_record["fixture_id"],
                    "fixture_path": fixture_record["path"],
                    "repetition": repetition,
                    "document_variant": variant,
                    "policy": policy,
                    "handoff": handoff,
                    "fault": fault,
                }
                condition["attempt_key"] = _condition_id(
                    fixture_record["fixture_id"], repetition, variant, policy, handoff, fault
                )
                condition["state_mode"] = "fresh"
                condition["chain_id"] = None
                condition["handoff_snapshot_key"] = (
                    f"{fixture_record['fixture_id']}-r{repetition}-{variant}-H1"
                    if handoff == "H1" else None
                )
                attempts.append((_order_key(seed, block_id, condition), condition))
            attempts.sort(key=lambda item: item[0])
            blocks.append({
                "block_id": block_id,
                "fixture_id": fixture_record["fixture_id"],
                "repetition": repetition,
                "attempts": [condition for _key, condition in attempts],
            })
    attempt_count = sum(len(block["attempts"]) for block in blocks)
    return {
        "schema_version": PLAN_VERSION,
        "seed": seed,
        "repetitions": repetitions,
        "dimensions": {name: list(values) for name, values in dimensions.items()},
        "fixtures": fixture_records,
        "block_count": len(blocks),
        "attempt_count": attempt_count,
        "ordering": "sha256(seed, block_id, condition) within fixture/repetition blocks",
        "state_policy": "fresh state per ordinary attempt; only declared chains retain memory",
        "blocks": blocks,
    }


def plan_sha256(plan: dict[str, Any]) -> str:
    return _sha256_bytes(_json_bytes(plan))


def validate_plan(plan: dict[str, Any], *, verify_fixtures: bool = True) -> None:
    """Reject incomplete matrices, duplicate attempts and changed fixture bytes."""
    if not isinstance(plan, dict) or plan.get("schema_version") != PLAN_VERSION:
        raise RunnerError("invalid_plan_version")
    dimensions = plan.get("dimensions")
    if not isinstance(dimensions, dict):
        raise RunnerError("invalid_plan_dimensions")
    repetitions = plan.get("repetitions")
    if type(repetitions) is not int or repetitions < 1 or not isinstance(plan.get("seed"), str):
        raise RunnerError("invalid_plan_settings")
    for name, allowed in (("policies", POLICIES), ("handoffs", HANDOFFS),
                          ("faults", FAULTS), ("document_variants", DOCUMENT_VARIANTS)):
        values = dimensions.get(name)
        if not isinstance(values, list) or not values or len(values) != len(set(values)):
            raise RunnerError("invalid_plan_" + name)
        if not set(values) <= set(allowed):
            raise RunnerError("invalid_plan_" + name)
    fixtures = plan.get("fixtures")
    blocks = plan.get("blocks")
    if not isinstance(fixtures, list) or not isinstance(blocks, list):
        raise RunnerError("invalid_plan_structure")
    fixture_map = {}
    for record in fixtures:
        if not isinstance(record, dict) or set(record) != {"fixture_id", "path", "sha256"}:
            raise RunnerError("invalid_fixture_record")
        if record["fixture_id"] in fixture_map:
            raise RunnerError("duplicate_fixture_id")
        fixture_map[record["fixture_id"]] = record
        if verify_fixtures:
            path = _resolve_path(record["path"])
            fixture = load_fixture(path)
            if fixture["fixture_id"] != record["fixture_id"]:
                raise RunnerError("fixture_id_changed")
            if _sha256_bytes(path.read_bytes()) != record["sha256"]:
                raise RunnerError("fixture_bytes_changed")
    expected_per_block = (
        len(dimensions["policies"]) * len(dimensions["handoffs"])
        * len(dimensions["faults"]) * len(dimensions["document_variants"])
    )
    seen_attempts = set()
    expected_blocks = {
        (fixture_id, repetition)
        for fixture_id in fixture_map
        for repetition in range(1, repetitions + 1)
    }
    actual_blocks = set()
    for block in blocks:
        if not isinstance(block, dict) or not isinstance(block.get("attempts"), list):
            raise RunnerError("invalid_block")
        key = (block.get("fixture_id"), block.get("repetition"))
        if key in actual_blocks:
            raise RunnerError("duplicate_block")
        actual_blocks.add(key)
        if key not in expected_blocks or block.get("block_id") != f"{key[0]}-r{key[1]}":
            raise RunnerError("invalid_block_identity")
        attempts = block["attempts"]
        if len(attempts) != expected_per_block:
            raise RunnerError("incomplete_block")
        combinations = set()
        for attempt in attempts:
            required = {"attempt_key", "fixture_id", "fixture_path", "repetition",
                        "document_variant", "policy", "handoff", "fault", "state_mode",
                        "chain_id", "handoff_snapshot_key"}
            if not isinstance(attempt, dict) or set(attempt) != required:
                raise RunnerError("invalid_attempt")
            if attempt["attempt_key"] in seen_attempts:
                raise RunnerError("duplicate_attempt_key")
            seen_attempts.add(attempt["attempt_key"])
            if (attempt["fixture_id"], attempt["repetition"]) != key:
                raise RunnerError("attempt_outside_block")
            fixture_record = fixture_map[attempt["fixture_id"]]
            if attempt["fixture_path"] != fixture_record["path"]:
                raise RunnerError("attempt_fixture_path_changed")
            for name, field in (("document_variants", "document_variant"),
                                ("policies", "policy"), ("handoffs", "handoff"),
                                ("faults", "fault")):
                if attempt[field] not in dimensions[name]:
                    raise RunnerError("attempt_outside_dimensions")
            expected_key = _condition_id(
                attempt["fixture_id"], attempt["repetition"], attempt["document_variant"],
                attempt["policy"], attempt["handoff"], attempt["fault"]
            )
            if attempt["attempt_key"] != expected_key:
                raise RunnerError("attempt_key_changed")
            if attempt["state_mode"] != "fresh" or attempt["chain_id"] is not None:
                raise RunnerError("ordinary_attempt_must_be_fresh")
            expected_snapshot = (
                f"{attempt['fixture_id']}-r{attempt['repetition']}-{attempt['document_variant']}-H1"
                if attempt["handoff"] == "H1" else None
            )
            if attempt["handoff_snapshot_key"] != expected_snapshot:
                raise RunnerError("handoff_snapshot_key_changed")
            combinations.add((attempt["document_variant"], attempt["policy"],
                              attempt["handoff"], attempt["fault"]))
        if len(combinations) != expected_per_block:
            raise RunnerError("duplicate_condition")
        ordered = sorted(attempts, key=lambda item: _order_key(plan["seed"], block["block_id"], item))
        if attempts != ordered:
            raise RunnerError("attempt_order_changed")
    if actual_blocks != expected_blocks:
        raise RunnerError("incomplete_blocks")
    if plan.get("block_count") != len(blocks) or plan.get("attempt_count") != len(seen_attempts):
        raise RunnerError("plan_count_mismatch")


def _relative(path: Path, parent: Path) -> str:
    try:
        return path.resolve().relative_to(parent.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _load_result(directory: Path, returned: Any) -> dict[str, Any]:
    if isinstance(returned, dict):
        return deepcopy(returned)
    path = directory / "result.json"
    if path.is_file():
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return value
    raise RunnerError("executor_result_missing")


def _reset_ok(result: dict[str, Any], directory: Path) -> bool:
    reset = result.get("reset")
    if not isinstance(reset, dict) and (directory / "reset.json").is_file():
        try:
            reset = json.loads((directory / "reset.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            return False
    return bool(
        isinstance(reset, dict)
        and reset.get("bindings_after") == 0
        and reset.get("conversation_cleared") is True
        and reset.get("audit_preserved") is True
    )


def _bundle_metrics(path: Path) -> dict[str, Any] | None:
    """Retain observations from valid partial as well as finished bundles."""
    try:
        bundle = load_json(path)
        validate("bundle", bundle)
        return trace_metrics(bundle["trace"])
    except (OSError, ValueError, ContractError):
        return None


def snapshot_sha256(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except FileNotFoundError:
        raise RunnerError("h1_snapshot_missing") from None
    except OSError:
        raise RunnerError("h1_snapshot_unreadable") from None


def _prepare_snapshot(provider, condition, directory, root, record):
    """Record generation evidence even when generation fails."""
    directory.mkdir(parents=True)
    path = None
    try:
        path = Path(provider(deepcopy(condition), directory)).resolve()
        record["sha256"] = snapshot_sha256(path)
        record["path"] = _relative(path, root)
    except KeyboardInterrupt:
        record["error_type"] = "runner_interrupted"
        raise
    except Exception as exc:
        record["error_type"] = (str(exc) if isinstance(exc, RunnerError)
                                else "snapshot_provider_" + type(exc).__name__)
    finally:
        candidates = {p.resolve() for p in directory.rglob("generation-bundle.json")}
        if path is not None and (path.parent / "generation-bundle.json").is_file():
            candidates.add(path.parent / "generation-bundle.json")
        paths = sorted(candidates)
        record["generation_bundle_paths"] = [_relative(p, root) for p in paths]
        record["generation_observations"] = [_bundle_metrics(p) for p in paths]
        if len(paths) == 1:
            record["generation_bundle_path"] = record["generation_bundle_paths"][0]
            record["generation_metrics"] = record["generation_observations"][0]
        record["generation_error_type"] = record["error_type"]


def _check_snapshot(path, snapshot):
    if snapshot_sha256(path) != snapshot["sha256"]:
        raise RunnerError("h1_snapshot_changed")


def _record_snapshot_use(target, execution, snapshot):
    used_artifact = target / "handoff-artifact.json"
    if used_artifact.is_file():
        execution["used_snapshot_path"] = (Path(execution["output_dir"]) / used_artifact.name).as_posix()
        try:
            execution["snapshot_sha256"] = snapshot_sha256(used_artifact)
        except RunnerError:
            pass
    needs_artifact = execution["status"] == "completed" or execution["bundle_path"] is not None
    if needs_artifact and execution["snapshot_sha256"] != snapshot["sha256"]:
        raise RunnerError("h1_snapshot_use_mismatch")


def run_plan(
    plan: dict[str, Any],
    output_dir: str | Path,
    executor: Callable[[dict[str, Any], Path, Path | None], Any],
    *,
    snapshot_provider: Callable[[dict[str, Any], Path], str | Path] | None = None,
    after_condition: Callable[[dict[str, Any]], None] | None = None,
    max_retries: int = 0,
    retryable_errors: Iterable[str] = (),
) -> dict[str, Any]:
    """Execute a plan without carrying mutable state between ordinary attempts.

    ``executor`` receives a copied condition, a new output path, and either the
    immutable H1 snapshot path or ``None``. It must create its output directory.
    Every try is retained. A retry occurs only for an explicitly declared error.
    An optional observer can stop the run after the condition's evidence is saved.
    """
    validate_plan(plan)
    if type(max_retries) is not int or max_retries < 0:
        raise RunnerError("invalid_retry_limit")
    retryable = set(retryable_errors)
    if any(not isinstance(item, str) or not item for item in retryable):
        raise RunnerError("invalid_retryable_error")
    if snapshot_provider is None and any(
        attempt["handoff"] == "H1"
        for block in plan["blocks"] for attempt in block["attempts"]
    ):
        raise RunnerError("h1_snapshot_provider_required")
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    _write_json(root / "plan.json", plan)
    ledger = {
        "schema_version": LEDGER_VERSION,
        "plan_sha256": plan_sha256(plan),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "max_retries": max_retries,
        "retryable_errors": sorted(retryable),
        "snapshots": [],
        "attempts": [],
    }
    ledger_path = root / "run-ledger.json"
    _write_ledger(ledger_path, ledger)
    snapshots: dict[str, dict[str, Any]] = {}
    ordinal = 0
    for block in plan["blocks"]:
        for planned in block["attempts"]:
            ordinal += 1
            attempt_record = {
                "ordinal": ordinal,
                "attempt_key": planned["attempt_key"],
                "condition": deepcopy(planned),
                "executions": [],
                "selected_try": None,
                "preparation_error": None,
            }
            ledger["attempts"].append(attempt_record)
            snapshot_path = None
            snapshot_key = planned["handoff_snapshot_key"]
            snapshot = None
            if snapshot_key is not None:
                if snapshot_key not in snapshots:
                    snapshot = {
                        "snapshot_key": snapshot_key, "path": None, "sha256": None,
                        "generation_bundle_path": None, "generation_metrics": None,
                        "error_type": None,
                    }
                    snapshots[snapshot_key] = snapshot
                    ledger["snapshots"].append(snapshot)
                    try:
                        _prepare_snapshot(snapshot_provider, planned, root / "snapshots" / snapshot_key,
                                          root, snapshot)
                    except KeyboardInterrupt:
                        attempt_record["preparation_error"] = snapshot["error_type"]
                        raise
                    finally:
                        _write_ledger(ledger_path, ledger)
                snapshot = snapshots[snapshot_key]
                if snapshot["error_type"] is None:
                    snapshot_path = root / snapshot["path"]
            for try_number in range(1, max_retries + 2):
                if snapshot is not None:
                    try:
                        if snapshot["error_type"] is None:
                            _check_snapshot(snapshot_path, snapshot)
                    except RunnerError as exc:
                        snapshot["error_type"] = str(exc)
                    if snapshot["error_type"] is not None:
                        attempt_record["preparation_error"] = snapshot["error_type"]
                        _write_ledger(ledger_path, ledger)
                        break
                target = root / "attempts" / f"{ordinal:04d}-{planned['attempt_key']}" / f"try-{try_number:02d}"
                target.parent.mkdir(parents=True, exist_ok=True)
                execution = {
                    "try": try_number,
                    "output_dir": _relative(target, root),
                    "status": "error",
                    "error_type": None,
                    "reset_ok": False,
                    "bundle_path": None,
                    "result_path": None,
                    "outcome_path": None,
                    "snapshot_sha256": None,
                    "used_snapshot_path": None,
                    "metrics": None,
                }
                interrupted = False
                try:
                    returned = executor(deepcopy(planned), target, snapshot_path)
                    result = _load_result(target, returned)
                    if not (target / "result.json").is_file():
                        target.mkdir(parents=True, exist_ok=True)
                        _write_json(target / "result.json", result)
                    status = result.get("status")
                    error_type = result.get("error_type")
                    if status not in {"completed", "incomplete", "error"}:
                        raise RunnerError("invalid_executor_status")
                    if error_type is not None and not isinstance(error_type, str):
                        raise RunnerError("invalid_executor_error")
                    execution["status"] = status
                    execution["error_type"] = error_type
                    execution["reset_ok"] = _reset_ok(result, target)
                except KeyboardInterrupt:
                    execution["error_type"] = "runner_interrupted"
                    interrupted = True
                except Exception as exc:  # Evidence keeps the type, never arbitrary text.
                    execution["error_type"] = (
                        str(exc) if isinstance(exc, RunnerError) else "executor_" + type(exc).__name__
                    )
                for name, field in (("bundle.json", "bundle_path"),
                                    ("result.json", "result_path"),
                                    ("outcome.json", "outcome_path")):
                    path = target / name
                    if path.is_file():
                        execution[field] = _relative(path, root)
                execution["metrics"] = _bundle_metrics(target / "bundle.json")
                if snapshot_path is not None:
                    try:
                        _check_snapshot(snapshot_path, snapshot)
                    except RunnerError as exc:
                        snapshot["error_type"] = str(exc)
                    try:
                        _record_snapshot_use(target, execution, snapshot)
                    except RunnerError as exc:
                        if not interrupted:
                            execution.update(status="error", error_type=str(exc))
                    if snapshot["error_type"] is not None and not interrupted:
                        execution.update(status="error", error_type=snapshot["error_type"])
                if not execution["reset_ok"]:
                    execution["status"] = "error"
                    execution["error_type"] = execution["error_type"] or "attempt_reset_failed"
                attempt_record["executions"].append(execution)
                attempt_record["selected_try"] = try_number
                _write_ledger(ledger_path, ledger)
                if interrupted:
                    raise KeyboardInterrupt
                if snapshot is not None and snapshot["error_type"] is not None:
                    break
                if execution["status"] == "completed":
                    break
                if execution["error_type"] not in retryable or try_number > max_retries:
                    break
            if after_condition is not None:
                after_condition(deepcopy(attempt_record))
    ledger["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_ledger(ledger_path, ledger)
    return ledger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new JSON plan path")
    parser.add_argument("--seed", default="dase7508-core-v1")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--fixtures", type=Path, default=ROOT / "fixtures" / "benign")
    args = parser.parse_args(argv)
    try:
        paths = sorted(args.fixtures.glob("B*.json"))
        plan = build_core_plan(paths, repetitions=args.repetitions, seed=args.seed)
        validate_plan(plan)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(plan, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
    except (OSError, ValueError, UnicodeError) as exc:
        print(str(exc), file=__import__("sys").stderr)
        return 2
    print(f"Wrote {plan['attempt_count']} attempts in {plan['block_count']} blocks to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
