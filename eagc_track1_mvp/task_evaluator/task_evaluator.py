from typing import Any, Dict, List


def evaluate_task_status(
    task: str,
    world_model: Dict[str, Any],
    episode_id: str,
    evaluator_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    del task
    evaluator_context = evaluator_context or {}
    success_condition = evaluator_context.get("success_condition")
    if isinstance(success_condition, dict) and success_condition:
        return _evaluate_success_condition(success_condition, world_model)
    if episode_id in {"mock-bedroom-relocated", "visual-bedroom-smoke", "local-explore-book-relocated"}:
        return _object_on_support(world_model, "book", "chair")
    if episode_id == "local-door-locked-route":
        if _location_support(world_model, "cup") == "counter" and world_model.get("agent_state", {}).get(
            "current_room"
        ) == "kitchen":
            return _status(
                "complete",
                True,
                "Agent reached kitchen and placed the cup on the counter.",
                ["agent current_room kitchen", "cup support counter"],
            )
        return _status("in_progress", False, "Cup is not yet on the kitchen counter.", [])
    if episode_id == "local-container-unavailable":
        drawer_unavailable = _has_state(world_model, "drawer", "availability", "unavailable")
        cup_on_counter = _location_support(world_model, "cup") == "counter"
        if drawer_unavailable and cup_on_counter:
            return _status(
                "blocked_recovered",
                True,
                "Drawer is unavailable; cup was placed on the counter as fallback.",
                ["drawer availability unavailable", "cup support counter"],
            )
        if _location_support(world_model, "cup") == "drawer":
            return _status("complete", True, "Cup is in the drawer.", ["cup support drawer"])
        return _status("in_progress", False, "Cup has not reached a valid final support.", [])
    if episode_id == "local-tool-substitution":
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


def _evaluate_success_condition(condition: Dict[str, Any], world_model: Dict[str, Any]) -> Dict[str, Any]:
    condition_type = condition.get("type")
    expected_status = str(condition.get("status") or "complete")
    if condition_type == "object_on_support":
        obj = str(condition.get("object", ""))
        target = str(condition.get("target", ""))
        if _location_support(world_model, obj) == target:
            return _status(expected_status, True, f"{obj} is on {target}.", [f"{obj}.location.support == {target}"])
        return _status("in_progress", False, f"{obj} is not on {target}.", [])

    if condition_type == "object_in_container":
        obj = str(condition.get("object", ""))
        target = str(condition.get("target", ""))
        if _location_support(world_model, obj) == target or _has_relation(world_model, obj, "inside", target):
            return _status(expected_status, True, f"{obj} is inside {target}.", [f"{obj} inside {target}"])
        return _status("in_progress", False, f"{obj} is not inside {target}.", [])

    if condition_type == "agent_room_and_object_on_support":
        room = str(condition.get("room", ""))
        obj = str(condition.get("object", ""))
        target = str(condition.get("target", ""))
        if world_model.get("agent_state", {}).get("current_room") == room and _location_support(world_model, obj) == target:
            return _status(
                expected_status,
                True,
                f"Agent reached {room} and placed {obj} on {target}.",
                [f"agent current_room {room}", f"{obj}.location.support == {target}"],
            )
        return _status("in_progress", False, f"Agent/object condition for {obj} on {target} in {room} is unmet.", [])

    if condition_type == "tool_substitution":
        target = str(condition.get("target", ""))
        substitute = str(condition.get("substitute_tool", ""))
        if _has_state(world_model, target, "tightened_by", substitute) or _has_state(world_model, target, "status", "tightened"):
            return _status(
                expected_status,
                True,
                f"{target} was completed with substitute tool {substitute}.",
                [f"{target} tightened_by {substitute}"],
            )
        return _status("in_progress", False, f"{target} has not been completed with {substitute}.", [])

    if condition_type == "fallback_placement":
        obj = str(condition.get("object", ""))
        target = str(condition.get("target", ""))
        fallback_target = str(condition.get("fallback_target", ""))
        if _location_support(world_model, obj) == fallback_target:
            return _status(
                "blocked_recovered",
                True,
                f"{target} was unavailable; {obj} was placed on fallback target {fallback_target}.",
                [f"{obj}.location.support == {fallback_target}"],
            )
        if _location_support(world_model, obj) == target or _has_relation(world_model, obj, "inside", target):
            return _status("complete", True, f"{obj} reached primary target {target}.", [f"{obj} support {target}"])
        return _status("in_progress", False, f"{obj} has not reached {target} or fallback {fallback_target}.", [])

    if condition_type == "unrecoverable":
        obj = str(condition.get("object", ""))
        target = str(condition.get("target", ""))
        if _location_support(world_model, obj) == target or _has_relation(world_model, obj, "inside", target):
            return _status("complete", True, f"{obj} unexpectedly reached primary target {target}.", [f"{obj} support {target}"])
        return _status("failed", False, f"Unrecoverable condition remained unresolved for {obj} -> {target}.", [])

    return _status("in_progress", False, f"Unsupported success_condition type {condition_type!r}.", [])


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


def _has_relation(world_model: Dict[str, Any], subject: str, relation_name: str, obj: str) -> bool:
    for relation in world_model.get("relations", []):
        if (
            isinstance(relation, dict)
            and relation.get("subject") == subject
            and relation.get("relation") == relation_name
            and relation.get("object") == obj
            and relation.get("status") == "active"
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
