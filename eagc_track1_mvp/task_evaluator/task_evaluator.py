from typing import Any, Dict, List


def evaluate_task_status(task: str, world_model: Dict[str, Any], episode_id: str) -> Dict[str, Any]:
    del task
    if episode_id in {"mock-bedroom-relocated", "visual-bedroom-smoke"}:
        return _object_on_support(world_model, "book", "chair")
    if episode_id == "mock-livingroom-nominal":
        return _object_on_support(world_model, "remote", "coffee_table")
    if episode_id == "mock-hallway-door-locked":
        if world_model.get("agent_state", {}).get("current_room") == "next_room" or _has_state(
            world_model, "agent", "location", "next_room"
        ):
            return _status("complete", True, "Agent entered next_room.", ["agent location next_room"])
        return _status("in_progress", False, "Agent has not entered next_room.", [])
    if episode_id == "mock-kitchen-container-unavailable":
        drawer_unavailable = _has_state(world_model, "drawer", "availability", "unavailable")
        cup_on_counter = _location_support(world_model, "cup") == "counter"
        if drawer_unavailable and cup_on_counter:
            return _status(
                "blocked_recovered",
                True,
                "Drawer is unavailable; cup was placed on the counter as a safe fallback.",
                ["drawer availability unavailable", "cup support counter"],
            )
        if _location_support(world_model, "cup") == "drawer":
            return _status("complete", True, "Cup is on the drawer.", ["cup support drawer"])
        return _status("in_progress", False, "Cup has not reached a valid final support.", [])
    if episode_id == "mock-study-tool-substitution":
        if _has_state(world_model, "loose_screw", "tightened_by", "coin") or _has_state(
            world_model, "loose_screw", "status", "tightened"
        ):
            return _status(
                "complete",
                True,
                "Loose screw was tightened with the substitute coin.",
                ["loose_screw tightened_by coin"],
            )
        return _status("in_progress", False, "Loose screw is not tightened yet.", [])
    return _status("in_progress", False, f"No evaluator rule for episode {episode_id}.", [])


def _object_on_support(world_model: Dict[str, Any], object_name: str, support: str) -> Dict[str, Any]:
    current_support = _location_support(world_model, object_name)
    if current_support == support:
        return _status(
            "complete",
            True,
            f"{object_name} is on {support}.",
            [f"{object_name}.location.support == {support}"],
        )
    return _status(
        "in_progress",
        False,
        f"{object_name} is not on {support}; current support is {current_support or 'unknown'}.",
        [],
    )


def _location_support(world_model: Dict[str, Any], object_name: str) -> str:
    obj = _find_object(world_model, object_name)
    if not obj:
        return ""
    location = obj.get("location", {})
    if not isinstance(location, dict):
        return ""
    return str(location.get("support") or "")


def _find_object(world_model: Dict[str, Any], object_name: str) -> Dict[str, Any] | None:
    for obj in world_model.get("objects", []):
        if isinstance(obj, dict) and (obj.get("name") == object_name or obj.get("id") == object_name):
            return obj
    return None


def _has_state(world_model: Dict[str, Any], entity: str, attribute: str, value: Any) -> bool:
    for state in world_model.get("states", []):
        if (
            isinstance(state, dict)
            and state.get("entity") == entity
            and state.get("attribute") == attribute
            and state.get("value") == value
        ):
            return True
    return False


def _status(status: str, success: bool, reason: str, evidence: List[str]) -> Dict[str, Any]:
    return {
        "task_status": status,
        "success": success,
        "reason": reason,
        "evidence": evidence,
    }
