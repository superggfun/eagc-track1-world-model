import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from planner.action_schema import parse_action
from validators.validate_local_sim_run import validate as validate_local_sim_run


def validate(world_model_path: Path, audit_path: Path, episode_log_path: Path) -> List[str]:
    errors: List[str] = []
    errors.extend(validate_local_sim_run(world_model_path, audit_path, episode_log_path))
    world_model = _read_json(world_model_path, errors, "world_model")
    audit = _read_json(audit_path, errors, "run_audit")
    rows = _read_jsonl(episode_log_path, errors)
    if errors:
        return errors

    if audit.get("env") != "local_sim_random":
        errors.append(f"run_audit.env must be local_sim_random, got {audit.get('env')!r}.")
    if "seed" not in audit:
        errors.append("run_audit.seed is required.")

    spec_path = Path(str(audit.get("generated_episode_spec_path", "")))
    if not spec_path.exists():
        errors.append(f"generated_episode_spec.json is missing: {spec_path}")
        spec = {}
    else:
        spec = _read_json(spec_path, errors, "generated_episode_spec")

    task_status = world_model.get("task_status", {})
    if not isinstance(task_status, dict) or not task_status.get("status"):
        errors.append("world_model.task_status.status is required.")

    score_path = Path(str(audit.get("track1_score_path", "")))
    if not score_path.exists():
        errors.append(f"track1_score.json is missing: {score_path}")

    hidden_spec = spec.get("hidden_spec", {}) if isinstance(spec, dict) else {}
    if not isinstance(hidden_spec, dict):
        hidden_spec = {}
    controlled_exception = hidden_spec.get("controlled_exception", spec.get("controlled_exception", {})) if isinstance(spec, dict) else {}
    if isinstance(controlled_exception, dict) and controlled_exception.get("type"):
        event_types = [row.get("event_type") for row in rows if isinstance(row, dict)]
        if task_status.get("status") != "blocked_recovered":
            for event_type in ["execution_exception", "replanning"]:
                if event_type not in event_types:
                    errors.append(f"controlled exception requires {event_type} in episode_log.")
            if "recovery_action" not in event_types:
                errors.append("controlled exception requires recovery_action in episode_log.")

    errors.extend(_validate_no_teleport_placement(world_model, rows))

    expected = str(audit.get("expected_task_status") or hidden_spec.get("expected_task_status") or spec.get("expected_task_status") or "")
    actual = str(task_status.get("status") or "")
    if expected and actual != expected:
        if not audit.get("accepted_failure"):
            errors.append(f"expected_task_status={expected}, got {actual}.")
        elif not audit.get("accepted_failure_reason"):
            errors.append("accepted_failure requires accepted_failure_reason.")
    return errors


def _validate_no_teleport_placement(world_model: Dict[str, Any], rows: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    final_room = str(world_model.get("agent_state", {}).get("current_room") or "")
    for row in rows:
        if row.get("result") != "success":
            continue
        action = str(row.get("action") or "")
        action_name, args = parse_action(action)
        if action_name not in {"place_on", "place_in"} or len(args) != 2:
            continue
        target_room = _object_room(world_model, args[1])
        placed_room = _object_room(world_model, args[0])
        if target_room and placed_room and target_room != placed_room:
            errors.append(f"{action} succeeded but placed object room {placed_room!r} differs from target room {target_room!r}.")
        if target_room and final_room and final_room != target_room and action == str(rows[-1].get("action", "")):
            errors.append(f"{action} appears to have teleported placement away from final agent room {final_room!r}.")
    return errors


def _object_room(world_model: Dict[str, Any], name: str) -> str:
    for obj in world_model.get("objects", []):
        if not isinstance(obj, dict):
            continue
        if obj.get("name") == name or obj.get("id") == name:
            location = obj.get("location")
            if isinstance(location, dict):
                return str(location.get("room") or "")
    return ""


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
        print("Random LocalSim validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Random LocalSim validation passed: {world_model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
