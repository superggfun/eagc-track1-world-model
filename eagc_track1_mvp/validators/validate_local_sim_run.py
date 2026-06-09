import json
import sys
from pathlib import Path
from typing import Any, Dict, List


EXPECTED_STATUS = {
    "local-explore-book-relocated": "complete",
    "local-door-locked-route": "complete",
    "local-container-unavailable": "blocked_recovered",
    "local-tool-substitution": "complete",
}

REQUIRED_EVENTS = {
    "perception",
    "world_model_update",
    "planning",
    "action",
    "task_evaluation",
}


def validate(world_model_path: Path, audit_path: Path, episode_log_path: Path) -> List[str]:
    errors: List[str] = []
    world_model = _read_json(world_model_path, errors, "world_model")
    audit = _read_json(audit_path, errors, "run_audit")
    rows = _read_jsonl(episode_log_path, errors)
    if errors:
        return errors

    if audit.get("env") != "local_sim":
        errors.append(f"run_audit.env must be local_sim, got {audit.get('env')!r}.")

    topology = world_model.get("topology")
    if not isinstance(topology, list) or not topology:
        errors.append("world_model.topology must be non-empty.")

    visited_rooms = world_model.get("visited_rooms")
    if not isinstance(visited_rooms, list) or not visited_rooms:
        errors.append("world_model.visited_rooms must be non-empty.")

    frontiers = world_model.get("frontiers")
    if not frontiers and not any(isinstance(node, dict) and node.get("frontiers") for node in topology or []):
        errors.append("world_model must record frontiers or explored room frontiers.")

    objects = world_model.get("objects")
    if not isinstance(objects, list) or not objects:
        errors.append("world_model.objects must be non-empty.")

    task_status = world_model.get("task_status")
    if not isinstance(task_status, dict) or not task_status.get("status"):
        errors.append("world_model.task_status.status is required.")
    else:
        expected = EXPECTED_STATUS.get(str(world_model.get("episode_id")))
        if expected and task_status.get("status") != expected:
            errors.append(
                f"{world_model.get('episode_id')} expected task_status={expected}, got {task_status.get('status')}."
            )

    event_types = [row.get("event_type") for row in rows if isinstance(row, dict)]
    missing = sorted(REQUIRED_EVENTS - set(event_types))
    if missing:
        errors.append(f"episode_log missing required LocalSim events: {missing}.")

    if world_model.get("exceptions"):
        if "replanning" not in event_types:
            errors.append("LocalSim exceptions require a replanning event.")
        if "recovery_action" not in event_types:
            errors.append("LocalSim exceptions require recovery_action execution.")

    return errors


def _read_json(path: Path, errors: List[str], label: str) -> Dict[str, Any]:
    if not path.exists():
        errors.append(f"Missing {label}: {path}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid {label} JSON: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{label} must be a JSON object.")
        return {}
    return data


def _read_jsonl(path: Path, errors: List[str]) -> List[Dict[str, Any]]:
    if not path.exists():
        errors.append(f"Missing episode_log: {path}")
        return []
    rows: List[Dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"episode_log line {line_number} is invalid JSON: {exc}")
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            errors.append(f"episode_log line {line_number} must be a JSON object.")
    return rows


def main() -> int:
    world_model_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/world_model.json")
    audit_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("outputs/run_audit.json")
    episode_log_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("outputs/episode_log.jsonl")
    errors = validate(world_model_path, audit_path, episode_log_path)
    if errors:
        print("LocalSim validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"LocalSim validation passed: {world_model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
