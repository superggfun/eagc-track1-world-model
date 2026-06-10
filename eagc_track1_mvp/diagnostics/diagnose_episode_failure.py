from __future__ import annotations

from typing import Any, Dict, List

from planner.action_schema import parse_action


def diagnose_failure(
    world_model: Dict[str, Any],
    episode_log: List[Dict[str, Any]],
    run_audit: Dict[str, Any],
    generated_episode_spec: Dict[str, Any],
) -> Dict[str, Any]:
    """Return a compact diagnosis for a failed or partially recovered episode."""
    task_status = world_model.get("task_status", {})
    status = str(task_status.get("status") or "")
    if status in {"complete", "blocked_recovered"}:
        return _diagnosis(
            "no_failure",
            str(task_status.get("reason") or "Task completed."),
            [f"task_status={status}"],
            "No repair needed for this replay.",
        )
    hidden_spec = generated_episode_spec.get("hidden_spec", {})
    if not isinstance(hidden_spec, dict):
        hidden_spec = {}
    condition = hidden_spec.get("success_condition", {})
    controlled_exception = hidden_spec.get("controlled_exception", {})
    if not isinstance(condition, dict):
        condition = {}
    if not isinstance(controlled_exception, dict):
        controlled_exception = {}

    executed_actions = _actions(episode_log)
    failed_actions = _failed_actions(episode_log)
    evidence: List[str] = []

    if controlled_exception.get("type") == "door_locked":
        door = str(controlled_exception.get("object") or "")
        target_room = str(condition.get("room") or _room_from_door(door))
        if door and _has_state(world_model, door, "lock_state", "unlocked") and not _has_action(executed_actions, "open", door):
            return _diagnosis(
                "key_found_but_not_used",
                f"{door} was unlocked or key recovery started, but open({door}) was not completed.",
                [f"door={door}", *failed_actions],
                f"Ensure recovery actions include unlock({door}) and open({door}) before resuming.",
            )
        if door and _has_state(world_model, door, "status", "open") and target_room and _current_room(world_model) != target_room:
            return _diagnosis(
                "door_unlocked_but_not_entered",
                f"{door} is open but agent current_room is {_current_room(world_model)!r}, not {target_room!r}.",
                [f"door={door}", f"target_room={target_room}", *failed_actions],
                f"After open({door}), resume or synthesize navigate_to({target_room}).",
            )
        if target_room and not _has_action(executed_actions, "navigate_to", target_room) and not _has_action(executed_actions, "enter", target_room):
            return _diagnosis(
                "target_room_not_reached",
                f"No navigate_to({target_room}) or enter({target_room}) action was executed.",
                [f"target_room={target_room}", *failed_actions],
                f"Planner/replanner should keep navigate_to({target_room}) in the post-recovery plan.",
            )
        if "recovery_complete" in _event_types(episode_log) and status == "in_progress":
            return _diagnosis(
                "opened_door_but_original_plan_not_resumed",
                "Recovery completed, but the original task did not finish afterward.",
                [f"status_reason={task_status.get('reason', '')}", *failed_actions],
                "Procedure runner should resume remaining actions or request a continuation plan after recovery.",
            )

    if any(action.startswith("navigate_to(") and action.endswith(")") for action in executed_actions):
        bad_targets = [
            action
            for action in executed_actions
            if action.startswith("navigate_to(") and _target_category(world_model, _first_arg(action)) not in {"room", "door", "object", ""}
        ]
        if bad_targets:
            return _diagnosis(
                "navigated_to_object_instead_of_room",
                "Navigation target classification looks inconsistent.",
                bad_targets,
                "Normalize navigation targets to room/object semantics before applying action effects.",
            )

    if "replanning" in _event_types(episode_log) and "recovery_complete" not in _event_types(episode_log):
        return _diagnosis(
            "recovery_plan_incomplete",
            "A recovery plan was created but did not complete.",
            failed_actions,
            "Check Replanner actions and max_recovery_steps for missing route or tool actions.",
        )

    if _has_stale_active_conflict(world_model):
        return _diagnosis(
            "stale_world_model_state",
            "World model contains potentially stale active state after execution.",
            ["location relation/state conflict detected"],
            "Apply action effects to stale old location relations and held_by state after movement or placement.",
        )

    return _diagnosis(
        "unknown_or_task_specific_failure",
        str(task_status.get("reason") or "No specific diagnosis matched."),
        [*failed_actions, f"run_status={run_audit.get('validation_status', {})}"],
        "Inspect episode_log.jsonl and generated_episode_spec.json for a task-specific planner gap.",
    )


def _diagnosis(failure_type: str, cause: str, evidence: List[str], fix: str) -> Dict[str, Any]:
    return {
        "failure_type": failure_type,
        "likely_root_cause": cause,
        "evidence": [item for item in evidence if item],
        "suggested_fix": fix,
    }


def _actions(rows: List[Dict[str, Any]]) -> List[str]:
    return [str(row.get("action")) for row in rows if row.get("action")]


def _failed_actions(rows: List[Dict[str, Any]]) -> List[str]:
    failed = []
    for row in rows:
        if row.get("result") == "failure" and row.get("action"):
            failed.append(f"{row.get('event_type')}: {row.get('action')} -> {row.get('notes', '')}")
    return failed


def _event_types(rows: List[Dict[str, Any]]) -> set[str]:
    return {str(row.get("event_type")) for row in rows if row.get("event_type")}


def _has_action(actions: List[str], name: str, arg: str) -> bool:
    return any(parse_action(action) == (name, [arg]) for action in actions)


def _first_arg(action: str) -> str:
    _name, args = parse_action(action)
    return args[0] if args else ""


def _current_room(world_model: Dict[str, Any]) -> str:
    agent_state = world_model.get("agent_state", {})
    if not isinstance(agent_state, dict):
        return ""
    return str(agent_state.get("current_room") or "")


def _room_from_door(door: str) -> str:
    if door == "kitchen_door":
        return "kitchen"
    if door == "living_room_door":
        return "living_room"
    if door == "bedroom_door":
        return "bedroom"
    return ""


def _has_state(world_model: Dict[str, Any], entity: str, attribute: str, value: str) -> bool:
    for state in world_model.get("states", []):
        if isinstance(state, dict) and state.get("entity") == entity and state.get("attribute") == attribute and state.get("value") == value:
            return True
    return False


def _target_category(world_model: Dict[str, Any], target: str) -> str:
    rooms = set(world_model.get("rooms", []))
    if target in rooms:
        return "room"
    if target.endswith("_door"):
        return "door"
    for obj in world_model.get("objects", []):
        if isinstance(obj, dict) and (obj.get("name") == target or obj.get("id") == target):
            return "object"
    return ""


def _has_stale_active_conflict(world_model: Dict[str, Any]) -> bool:
    active_locations: Dict[str, int] = {}
    for relation in world_model.get("relations", []):
        if not isinstance(relation, dict):
            continue
        if relation.get("status") == "active" and relation.get("relation") in {"on", "inside", "under", "near", "beside", "at"}:
            subject = str(relation.get("subject") or "")
            active_locations[subject] = active_locations.get(subject, 0) + 1
    return any(count > 1 for count in active_locations.values())
