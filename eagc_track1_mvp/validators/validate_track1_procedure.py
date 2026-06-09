import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from planner.action_schema import parse_action


REQUIRED_ORDER = [
    "exploration_start",
    "exploration_end",
    "task_received",
    "planning",
    "execution_start",
    "task_evaluation",
]

EXPLORATION_ACTIONS = {"explore", "navigate_to", "search"}
TASK_SPECIFIC_TARGETS = {
    "book",
    "chair",
    "cup",
    "drawer",
    "counter",
    "screwdriver",
    "coin",
    "loose_screw",
}


def validate(world_model_path: Path, audit_path: Path, episode_log_path: Path) -> List[str]:
    errors: List[str] = []
    world_model = _read_json(world_model_path, errors, "world_model")
    audit = _read_json(audit_path, errors, "run_audit")
    rows = _read_jsonl(episode_log_path, errors)
    if errors:
        return errors

    errors.extend(_validate_event_order(rows))
    errors.extend(_validate_task_reception(rows, world_model))
    errors.extend(_validate_exploration_actions(rows))
    errors.extend(_validate_partial_observability(rows))
    errors.extend(_validate_world_model_fields(world_model))
    errors.extend(_validate_audit(audit))
    errors.extend(_validate_score(audit))
    return errors


def _validate_event_order(rows: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    positions: Dict[str, int] = {}
    for index, row in enumerate(rows):
        event_type = row.get("event_type")
        if event_type in REQUIRED_ORDER and event_type not in positions:
            positions[str(event_type)] = index
    for event_type in REQUIRED_ORDER:
        if event_type not in positions:
            errors.append(f"episode_log missing required procedure event: {event_type}")
    for earlier, later in zip(REQUIRED_ORDER, REQUIRED_ORDER[1:]):
        if earlier in positions and later in positions and positions[earlier] >= positions[later]:
            errors.append(f"{earlier} must appear before {later}.")
    return errors


def _validate_task_reception(rows: List[Dict[str, Any]], world_model: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    event_types = [row.get("event_type") for row in rows]
    try:
        exploration_end = event_types.index("exploration_end")
        task_received = event_types.index("task_received")
    except ValueError:
        return errors
    if task_received < exploration_end:
        errors.append("task_received cannot appear before exploration_end.")
    task = str(world_model.get("task", "")).strip()
    if task:
        for row in rows[: exploration_end + 1]:
            observation = str(row.get("observation", ""))
            notes = str(row.get("notes", ""))
            if task in observation or task in notes:
                errors.append("Exploration phase leaked the natural-language task.")
                break
    return errors


def _validate_exploration_actions(rows: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    in_exploration = False
    for row in rows:
        event_type = row.get("event_type")
        if event_type == "exploration_start":
            in_exploration = True
        elif event_type == "exploration_end":
            in_exploration = False
        if not in_exploration:
            continue
        action = str(row.get("action", ""))
        if not action:
            continue
        action_name, _args = parse_action(action)
        if action_name not in EXPLORATION_ACTIONS:
            errors.append(f"Exploration phase used non-exploration action: {action}")
        if any(arg in TASK_SPECIFIC_TARGETS for arg in _args):
            errors.append(f"Exploration phase used task-specific target before task reception: {action}")
    return errors


def _validate_partial_observability(rows: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    in_exploration = False
    for row in rows:
        event_type = row.get("event_type")
        if event_type == "exploration_start":
            in_exploration = True
            continue
        if event_type == "exploration_end":
            in_exploration = False
        if not in_exploration:
            continue
        model_update = row.get("model_update")
        if not isinstance(model_update, dict):
            continue
        topology = model_update.get("topology")
        if not isinstance(topology, list) or not topology:
            continue
        visited_count = sum(1 for node in topology if isinstance(node, dict) and node.get("visited") is True)
        if len(topology) >= 4 and visited_count == len(topology):
            errors.append("Exploration phase marked all topology rooms visited before exploration_end.")
            break
        for node in topology:
            if not isinstance(node, dict):
                continue
            frontiers = node.get("frontiers")
            frontier_count = len(frontiers) if isinstance(frontiers, list) else 0
            if node.get("visited") is False and frontier_count > 1:
                errors.append(
                    f"Exploration phase exposed full frontier details for unvisited room {node.get('room')!r}."
                )
                break
    return errors


def _validate_world_model_fields(world_model: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for field in ["visited_rooms", "frontiers", "topology"]:
        value = world_model.get(field)
        if not isinstance(value, list) or not value:
            errors.append(f"world_model.{field} must be a non-empty list.")
    return errors


def _validate_audit(audit: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    budgets = audit.get("track1_budgets")
    if not isinstance(budgets, dict):
        errors.append("run_audit.track1_budgets must be present.")
    else:
        for field in ["exploration_steps", "planning_steps", "execution_steps", "max_recovery_steps"]:
            if field not in budgets:
                errors.append(f"run_audit.track1_budgets missing {field}.")
    for field in [
        "exploration_steps_used",
        "planning_steps_used",
        "execution_steps_used",
        "recovery_steps_used",
        "total_steps_used",
        "phase_budget_exceeded",
        "track1_score_path",
        "track1_total_score",
    ]:
        if field not in audit:
            errors.append(f"run_audit missing procedure field: {field}")
    return errors


def _validate_score(audit: Dict[str, Any]) -> List[str]:
    score_path = Path(str(audit.get("track1_score_path", "")))
    if not score_path.exists():
        return [f"track1_score.json is missing: {score_path}"]
    try:
        score = json.loads(score_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"track1_score.json is invalid JSON: {exc}"]
    total = score.get("total_score")
    if not isinstance(total, (int, float)) or not 0 <= float(total) <= 100:
        return ["track1_score.total_score must be between 0 and 100."]
    return []


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
        print("Track 1 procedure validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Track 1 procedure validation passed: {world_model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
