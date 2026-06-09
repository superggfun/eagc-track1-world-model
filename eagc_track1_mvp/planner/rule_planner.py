from typing import Any, Dict, List


class RulePlanner:
    """Tiny deterministic planner for the Track 1 MVP demo task."""

    def plan(self, task: str, world_model: Dict[str, Any]) -> Dict[str, Any]:
        if "book" in task.lower() and "chair" in task.lower():
            actions = ["locate(book)", "pick_up(book)", "place_on(book, chair)"]
            subgoals = [
                "Confirm the book location.",
                "Acquire the book.",
                "Place the book on the chair.",
            ]
        else:
            actions = ["inspect_scene()"]
            subgoals = ["Gather more information about the task."]

        return {
            "planner": "RulePlanner",
            "task": task,
            "subgoals": subgoals,
            "actions": actions,
            "based_on_rooms": world_model.get("rooms", []),
        }

    def next_actions(self, plan: Dict[str, Any]) -> List[str]:
        return list(plan.get("actions", []))
