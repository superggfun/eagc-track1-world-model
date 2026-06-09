from typing import Any, Dict, List

from planner.action_schema import invalid_actions


class RulePlanner:
    """Tiny deterministic planner for the Track 1 MVP demo task."""

    def plan(self, task: str, world_model: Dict[str, Any]) -> Dict[str, Any]:
        task_lower = task.lower()
        if "bedroom to kitchen" in task_lower and "cup" in task_lower and "counter" in task_lower:
            actions = [
                "navigate_to(hallway)",
                "open(kitchen_door)",
                "navigate_to(kitchen)",
                "locate(cup)",
                "pick_up(cup)",
                "place_on(cup, counter)",
            ]
            subgoals = [
                "Move from bedroom toward the kitchen.",
                "Open the kitchen route.",
                "Acquire the cup.",
                "Place the cup on the counter.",
            ]
        elif "book" in task_lower and "chair" in task_lower:
            actions = ["locate(book)", "pick_up(book)", "place_on(book, chair)"]
            subgoals = [
                "Confirm the book location.",
                "Acquire the book.",
                "Place the book on the chair.",
            ]
        elif "door" in task_lower:
            actions = ["navigate_to(door)", "open(door)", "navigate_to(next_room)"]
            subgoals = ["Reach the door.", "Open the door.", "Move through the doorway."]
        elif "cup" in task_lower and "drawer" in task_lower:
            actions = ["navigate_to(cup)", "locate(cup)", "pick_up(cup)", "place_in(cup, drawer)"]
            subgoals = ["Navigate to the cup.", "Acquire the cup.", "Place the cup in the drawer."]
        elif "screw" in task_lower:
            actions = [
                "navigate_to(screwdriver)",
                "locate(screwdriver)",
                "pick_up(screwdriver)",
                "use_tool(screwdriver, loose_screw)",
            ]
            subgoals = ["Navigate to a suitable tool.", "Acquire the tool.", "Use the tool on the loose screw."]
        elif "remote" in task_lower and "coffee table" in task_lower:
            actions = ["locate(remote)", "pick_up(remote)", "place_on(remote, coffee_table)"]
            subgoals = ["Find the remote.", "Acquire the remote.", "Place it on the coffee table."]
        else:
            actions = ["wait()"]
            subgoals = ["Gather more information about the task."]

        invalid = invalid_actions(actions)
        if invalid:
            raise ValueError(f"RulePlanner produced invalid actions: {invalid}")

        return {
            "planner": "RulePlanner",
            "task": task,
            "subgoals": subgoals,
            "actions": actions,
            "based_on_rooms": world_model.get("rooms", []),
        }

    def next_actions(self, plan: Dict[str, Any]) -> List[str]:
        return list(plan.get("actions", []))
