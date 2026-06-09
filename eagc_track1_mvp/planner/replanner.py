from typing import Any, Dict

from world_model.update import mark_object_location_unknown


class Replanner:
    def recover(self, failure: Dict[str, Any], world_model: Dict[str, Any]) -> Dict[str, Any]:
        exception = failure.get("exception", {})
        object_name = exception.get("object", "target object")
        reason = failure.get("message", "Action failed during execution.")

        if object_name == "book":
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
        else:
            recovery_actions = ["inspect_scene()", "retry_or_request_help()"]
            recovery_subgoals = ["Collect more state information before retrying."]

        plan = {
            "planner": "Replanner",
            "trigger": reason,
            "subgoals": recovery_subgoals,
            "actions": recovery_actions,
        }
        world_model.setdefault("plans", []).append(plan)
        world_model.setdefault("exceptions", []).append(exception or {"message": reason})
        return plan
