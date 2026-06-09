import json
import sys
from pathlib import Path
from typing import Any, Dict, List


REQUIRED_FIELDS = [
    "timestamp",
    "step",
    "event_type",
    "observation",
    "model_update",
    "action",
    "result",
    "notes",
]
AUDIT_EVENT_TYPES = {
    "perception",
    "world_model_update",
    "planning",
    "action",
    "execution_exception",
    "replanning",
    "recovery_plan",
    "recovery_action",
    "recovery_complete",
    "recovery_failed",
}


def validate(path: Path) -> List[str]:
    errors: List[str] = []
    if not path.exists():
        return [f"Missing episode log file: {path}"]

    rows: List[Dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"Line {line_number} is invalid JSON: {exc}")
            continue
        if not isinstance(row, dict):
            errors.append(f"Line {line_number} must be a JSON object.")
            continue
        rows.append(row)
        for field in REQUIRED_FIELDS:
            if field not in row:
                errors.append(f"Line {line_number} missing required field: {field}")

    errors.extend(_validate_steps(rows))
    errors.extend(_validate_event_coverage(rows))
    errors.extend(_validate_exception_recovery(rows))
    return errors


def _validate_steps(rows: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    previous_step = None
    for index, row in enumerate(rows):
        step = row.get("step")
        if not isinstance(step, int):
            errors.append(f"Row {index + 1} step must be an integer.")
            continue
        if previous_step is not None and step <= previous_step:
            errors.append(f"Step values must be strictly increasing near row {index + 1}.")
        previous_step = step
    return errors


def _validate_event_coverage(rows: List[Dict[str, Any]]) -> List[str]:
    present = {row.get("event_type") for row in rows}
    covered = present & AUDIT_EVENT_TYPES
    if len(covered) < 4:
        return [
            "Episode log should include several audit event types from "
            f"{sorted(AUDIT_EVENT_TYPES)}; found {sorted(covered)}"
        ]
    return []


def _validate_exception_recovery(rows: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    for index, row in enumerate(rows):
        if row.get("event_type") == "execution_exception":
            later_events = [later.get("event_type") for later in rows[index + 1 :]]
            if "replanning" not in later_events:
                errors.append(
                    f"execution_exception at step {row.get('step')} has no later replanning event."
                )
        if row.get("event_type") == "replanning":
            later_events = [later.get("event_type") for later in rows[index + 1 :]]
            if not any(
                event in {"recovery_action", "recovery_complete", "recovery_failed"}
                for event in later_events
            ):
                errors.append(
                    f"replanning at step {row.get('step')} has no later recovery execution event."
                )

    for index, row in enumerate(rows):
        if row.get("result") == "failure" and row.get("event_type") in {"action", "recovery_action"}:
            later_events = [later.get("event_type") for later in rows[index + 1 :]]
            if row.get("event_type") == "action" and "replanning" not in later_events:
                errors.append(f"failed action at step {row.get('step')} has no later replanning event.")
    return errors


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/episode_log.jsonl")
    errors = validate(path)
    if errors:
        print("Episode log validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Episode log validation passed: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
