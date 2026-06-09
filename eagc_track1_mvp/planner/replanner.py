from typing import Any, Dict

from planner.action_schema import invalid_actions
from world_model.update import mark_object_location_unknown


class Replanner:
    def recover(self, failure: Dict[str, Any], world_model: Dict[str, Any]) -> Dict[str, Any]:
        exception = failure.get("exception", {})
        object_name = exception.get("object", "target object")
        reason = failure.get("message", "Action failed during execution.")

        exception_type = exception.get("type", "unknown_exception")

        if exception_type == "object_relocated":
            recovery_actions = _search_actions_for_object(world_model, object_name)
            mark_object_location_unknown(world_model, object_name, reason)
            recovery_actions.extend([f"pick_up({object_name})", _resume_place_action(world_model, object_name)])
            recovery_subgoals = [
                f"Mark the {object_name} location as unknown.",
                "Search likely nearby locations.",
                "Resume the original task after finding the relocated object.",
            ]
        elif exception_type == "door_locked":
            recovery_actions = ["search(key_hook)", "search(under_mat)", "unlock(door)", "open(door)"]
            recovery_subgoals = ["Identify lock state.", "Search likely key locations.", "Unlock and retry."]
        elif exception_type == "target_container_unavailable":
            recovery_actions = ["locate(drawer)", "place_on(cup, counter)", "wait()"]
            recovery_subgoals = [
                "Confirm the target container is unavailable.",
                "Use a safe temporary placement.",
                "Record the blocked target.",
            ]
        elif exception_type == "tool_substitution":
            substitute = exception.get("substitute", "alternative_tool")
            recovery_actions = [
                f"substitute_tool({object_name}, {substitute})",
                f"pick_up({substitute})",
                "use_tool(coin, loose_screw)",
            ]
            recovery_subgoals = ["Confirm required tool is unavailable.", "Use a suitable substitute tool."]
        else:
            recovery_actions = ["wait()"]
            recovery_subgoals = ["Collect more state information before retrying."]

        invalid = invalid_actions(recovery_actions)
        if invalid:
            raise ValueError(f"Replanner produced invalid actions: {invalid}")

        plan = {
            "planner": "Replanner",
            "trigger": reason,
            "subgoals": recovery_subgoals,
            "actions": recovery_actions,
        }
        world_model.setdefault("plans", []).append(plan)
        world_model.setdefault("exceptions", []).append(
            {
                "event_type": "execution_exception",
                "exception": exception or {"message": reason},
                "recovery_plan": plan,
            }
        )
        return plan


def _search_actions_for_object(world_model: Dict[str, Any], object_name: str) -> list[str]:
    candidates: list[str] = []
    obj = _find_object(world_model, object_name)
    location = obj.get("location", {}) if obj else {}
    if isinstance(location, dict):
        for key in ["support", "region", "room"]:
            value = location.get(key)
            if value:
                candidates.append(str(value))

    for relation in world_model.get("relations", []):
        if not isinstance(relation, dict):
            continue
        if relation.get("subject") == object_name and relation.get("object"):
            candidates.append(str(relation["object"]))

    actions = []
    for candidate in candidates:
        action = f"search({candidate})"
        if action not in actions:
            actions.append(action)
    return actions or ["search(visible_area)"]


def _resume_place_action(world_model: Dict[str, Any], object_name: str) -> str:
    for plan in world_model.get("plans", []):
        if not isinstance(plan, dict):
            continue
        for action in plan.get("actions", []):
            if action.startswith(f"place_on({object_name},"):
                return action
    return f"place_on({object_name}, chair)"


def _find_object(world_model: Dict[str, Any], object_name: str) -> Dict[str, Any] | None:
    for obj in world_model.get("objects", []):
        if isinstance(obj, dict) and (obj.get("name") == object_name or obj.get("id") == object_name):
            return obj
    return None
