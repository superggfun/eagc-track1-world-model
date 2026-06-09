from typing import Any, Dict

from planner.action_schema import invalid_actions
from world_model.update import mark_object_location_unknown


class Replanner:
    def recover(self, failure: Dict[str, Any], world_model: Dict[str, Any]) -> Dict[str, Any]:
        exception = failure.get("exception", {})
        object_name = exception.get("object", "target object")
        reason = failure.get("message", "Action failed during execution.")

        exception_type = exception.get("type", "unknown_exception")

        if exception_type == "object_relocated" or object_name == "book":
            mark_object_location_unknown(world_model, "book", reason)
            recovery_actions = [
                "search(bed)",
                "search(under_pillow)",
                "search(beside_bed)",
                "search(chair)",
                "pick_up(book)",
                "place_on(book, chair)",
            ]
            recovery_subgoals = [
                "Mark the book location as unknown.",
                "Search likely nearby locations.",
                "Resume the original place-on-chair task after finding the book.",
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
            recovery_actions = [f"substitute_tool({object_name}, {substitute})", f"pick_up({substitute})"]
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
