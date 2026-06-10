import re
from typing import Any, Dict, List

from planner.action_schema import invalid_actions


class RulePlanner:
    """Tiny deterministic planner for the Track 1 MVP demo task."""

    def plan(self, task: str, world_model: Dict[str, Any]) -> Dict[str, Any]:
        task_lower = task.lower()
        generic_place_on = _parse_place_on(task_lower)
        generic_place_in = _parse_place_in(task_lower)
        target_room = _parse_go_to_room(task_lower)
        if generic_place_on and target_room:
            obj, target = generic_place_on
            actions = _route_to_room_actions(target_room)
            actions.extend(
                [
                    f"navigate_to({obj})",
                    f"locate({obj})",
                    f"pick_up({obj})",
                    f"navigate_to({target_room})",
                    f"navigate_to({target})",
                    f"place_on({obj}, {target})",
                ]
            )
            subgoals = [
                f"Open or verify the route to {target_room}.",
                f"Acquire the {obj}.",
                f"Return to {target_room} and place the {obj} on the {target}.",
            ]
        elif "bedroom to kitchen" in task_lower and "cup" in task_lower and "counter" in task_lower:
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
        elif generic_place_on:
            obj, target = generic_place_on
            actions = [f"navigate_to({obj})", f"locate({obj})", f"pick_up({obj})", f"navigate_to({target})", f"place_on({obj}, {target})"]
            subgoals = [
                f"Navigate to the {obj}.",
                f"Acquire the {obj}.",
                f"Place the {obj} on the {target}.",
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
        elif generic_place_in:
            obj, target = generic_place_in
            actions = [f"navigate_to({obj})", f"locate({obj})", f"pick_up({obj})", f"navigate_to({target})", f"place_in({obj}, {target})"]
            subgoals = [f"Navigate to the {obj}.", f"Acquire the {obj}.", f"Place the {obj} in the {target}."]
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


def _parse_place_on(task_lower: str) -> tuple[str, str] | None:
    match = re.search(r"place (?:the )?([a-z0-9_]+) on (?:the )?([a-z0-9_]+)", task_lower)
    if not match:
        return None
    return _resolve_pronoun(task_lower, match.group(1)), match.group(2)


def _parse_place_in(task_lower: str) -> tuple[str, str] | None:
    match = re.search(r"place (?:the )?([a-z0-9_]+) in (?:the )?([a-z0-9_]+)", task_lower)
    if not match:
        return None
    return _resolve_pronoun(task_lower, match.group(1)), match.group(2)


def _parse_go_to_room(task_lower: str) -> str:
    match = re.search(r"go (?:from [a-z0-9_]+ to|to) (?:the )?([a-z0-9_]+)", task_lower)
    return match.group(1) if match else ""


def _route_to_room_actions(room: str) -> list[str]:
    if room == "kitchen":
        return ["navigate_to(hallway)", "open(kitchen_door)", "navigate_to(kitchen)"]
    return [f"navigate_to({room})"]


def _resolve_pronoun(task_lower: str, value: str) -> str:
    if value != "it":
        return value
    match = re.search(r"find (?:the )?([a-z0-9_]+)", task_lower)
    return match.group(1) if match else value
