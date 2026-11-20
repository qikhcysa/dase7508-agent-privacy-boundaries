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
    """Retain cost observations in the ledger as well as in the raw bundle."""
    if not path.is_file():
        return None
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
        trace = bundle["trace"]
        attempts = [event for event in trace if event["event"] == "send_attempt"]
        results = [event for event in trace if event["event"] == "send_result"]
        metrics: dict[str, Any] = {
            "send_count": len(attempts),
            "outbound_bytes": sum(event["body"]["byte_length"] for event in attempts),
            "response_bytes": sum(
                event["response"]["byte_length"]
                for event in results if event["response"] is not None
            ),
            "latency_ms": sum(event["latency_ms"] for event in results),
        }
        for field in ("input_tokens", "output_tokens", "cost_usd"):
            values = [event["usage"][field] for event in results]
            known = [value for value in values if value is not None]
            metrics[field] = sum(known) if known else None
            metrics[field + "_unknown_results"] = len(values) - len(known)
        return metrics
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return None


def _execution_metrics(directory: Path) -> dict[str, Any] | None:
    return _bundle_metrics(directory / "bundle.json")


def run_plan(
    plan: dict[str, Any],
    output_dir: str | Path,
    executor: Callable[[dict[str, Any], Path, Path | None], Any],
    *,
    snapshot_provider: Callable[[dict[str, Any], Path], str | Path] | None = None,
    max_retries: int = 0,
    retryable_errors: Iterable[str] = (),
) -> dict[str, Any]:
    """Execute a plan without carrying mutable state between ordinary attempts.

    ``executor`` receives a copied condition, a new output path, and either the
    immutable H1 snapshot path or ``None``. It must create its output directory.
    Every try is retained. A retry occurs only for an explicitly declared error.
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
    snapshots: dict[str, tuple[Path, str]] = {}
    snapshot_errors: dict[str, str] = {}
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
            if snapshot_key is not None:
                if snapshot_key in snapshot_errors:
                    attempt_record["preparation_error"] = snapshot_errors[snapshot_key]
                    _write_ledger(ledger_path, ledger)
                    continue
                if snapshot_key not in snapshots:
                    (root / "snapshots").mkdir(parents=True, exist_ok=True)
                    try:
                        supplied = Path(snapshot_provider(deepcopy(planned), root / "snapshots"))
                        snapshot_path = supplied.resolve()
                        if not snapshot_path.is_file():
                            raise RunnerError("h1_snapshot_missing")
                    except Exception as exc:
                        error = (str(exc) if isinstance(exc, RunnerError)
                                 else "snapshot_provider_" + type(exc).__name__)
                        snapshot_errors[snapshot_key] = error
                        attempt_record["preparation_error"] = error
                        ledger["snapshots"].append({
                            "snapshot_key": snapshot_key,
                            "path": None,
                            "sha256": None,
                            "generation_bundle_path": None,
                            "generation_metrics": None,
                            "error_type": error,
                        })
                        _write_ledger(ledger_path, ledger)
                        continue
                    snapshot_hash = _sha256_bytes(snapshot_path.read_bytes())
                    snapshots[snapshot_key] = (snapshot_path, snapshot_hash)
                    generation_bundle = snapshot_path.parent / "generation-bundle.json"
                    ledger["snapshots"].append({
                        "snapshot_key": snapshot_key,
                        "path": _relative(snapshot_path, root),
                        "sha256": snapshot_hash,
                        "generation_bundle_path": (
                            _relative(generation_bundle, root) if generation_bundle.is_file() else None
                        ),
                        "generation_metrics": _bundle_metrics(generation_bundle),
                        "error_type": None,
                    })
                    _write_ledger(ledger_path, ledger)
                snapshot_path, expected_snapshot_hash = snapshots[snapshot_key]
                if _sha256_bytes(snapshot_path.read_bytes()) != expected_snapshot_hash:
                    snapshot_errors[snapshot_key] = "h1_snapshot_changed"
                    attempt_record["preparation_error"] = "h1_snapshot_changed"
                    next(item for item in ledger["snapshots"]
                         if item["snapshot_key"] == snapshot_key)["error_type"] = "h1_snapshot_changed"
                    _write_ledger(ledger_path, ledger)
                    continue
            for try_number in range(1, max_retries + 2):
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
                    "metrics": None,
                }
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
                    attempt_record["executions"].append(execution)
                    _write_ledger(ledger_path, ledger)
                    raise
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
                execution["metrics"] = _execution_metrics(target)
                if snapshot_path is not None:
                    current_hash = _sha256_bytes(snapshot_path.read_bytes())
                    execution["snapshot_sha256"] = current_hash
                    if current_hash != snapshots[snapshot_key][1]:
                        execution["status"] = "error"
                        execution["error_type"] = "h1_snapshot_changed"
                        snapshot_errors[snapshot_key] = "h1_snapshot_changed"
                        next(item for item in ledger["snapshots"]
                             if item["snapshot_key"] == snapshot_key)["error_type"] = "h1_snapshot_changed"
                if not execution["reset_ok"]:
                    execution["status"] = "error"
                    execution["error_type"] = execution["error_type"] or "attempt_reset_failed"
                attempt_record["executions"].append(execution)
                attempt_record["selected_try"] = try_number
                _write_ledger(ledger_path, ledger)
                if execution["status"] == "completed":
                    break
                if execution["error_type"] not in retryable or try_number > max_retries:
                    break
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
