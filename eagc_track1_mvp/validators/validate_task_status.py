import json
import sys
from pathlib import Path
from typing import Any, Dict, List


EXPECTED_STATUS = {
    "mock-bedroom-relocated": "complete",
    "mock-livingroom-nominal": "complete",
    "mock-hallway-door-locked": "complete",
    "mock-kitchen-container-unavailable": "blocked_recovered",
    "mock-study-tool-substitution": "complete",
    "local-explore-book-relocated": "complete",
    "local-door-locked-route": "complete",
    "local-container-unavailable": "blocked_recovered",
    "local-tool-substitution": "complete",
}


def validate(world_model_path: Path, episode_log_path: Path | None = None) -> List[str]:
    errors: List[str] = []
    if not world_model_path.exists():
        return [f"Missing world model file: {world_model_path}"]
    try:
        world_model = json.loads(world_model_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"Invalid world model JSON: {exc}"]

    task_status = world_model.get("task_status")
    if not isinstance(task_status, dict):
        return ["world_model is missing task_status object."]
    for field in ["status", "success", "reason", "evidence"]:
        if field not in task_status:
            errors.append(f"task_status missing field: {field}")

    episode_id = world_model.get("episode_id")
    expected = EXPECTED_STATUS.get(episode_id)
    actual = task_status.get("status")
    if expected and actual != expected:
        errors.append(f"{episode_id} expected task_status.status={expected}, got {actual}.")
    if actual in {"complete", "blocked_recovered"} and task_status.get("success") is not True:
        errors.append(f"task_status.success must be true for status={actual}.")

    if episode_log_path and episode_log_path.exists():
        rows = _read_log_rows(episode_log_path)
        if any(row.get("event_type") == "recovery_complete" for row in rows) and actual == "in_progress":
            errors.append("recovery_complete occurred but task_status is still in_progress.")

    return errors


def _read_log_rows(path: Path) -> List[Dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main() -> int:
    world_model_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/world_model.json")
    episode_log_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("outputs/episode_log.jsonl")
    errors = validate(world_model_path, episode_log_path)
    if errors:
        print("Task status validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Task status validation passed: {world_model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
