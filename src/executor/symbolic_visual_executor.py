from __future__ import annotations

from typing import Any, Dict

from planner.action_schema import parse_action
from task_evaluator.visual_task_evaluator import evaluate_visual_task


PHYSICAL_ACTIONS = {"pick_up", "place_on", "place_in", "open", "close", "unlock", "use_tool", "substitute_tool"}


class SymbolicVisualExecutor:
    """Plan-level executor for visual-only tasks.

    It never claims physical manipulation success. It only checks whether a
    symbolic answer can be supported by the current visual world model.
    """

    def __init__(self, world_model: Dict[str, Any], task: str) -> None:
        self.world_model = world_model
        self.task = task
        self.symbolic_action_count = 0
        self.unsupported_physical_action_count = 0

    def execute(self, action: str) -> Dict[str, Any]:
        self.symbolic_action_count += 1
        name, args = parse_action(action)
        if name in PHYSICAL_ACTIONS:
            self.unsupported_physical_action_count += 1
            return {
                "success": False,
                "result": "unsupported_in_visual_mode",
                "answer": "",
                "evidence": [],
                "message": f"{action} is a physical action and is unsupported in visual-only mode.",
            }

        if name in {"locate", "inspect"} and args:
            obj = _find_object(self.world_model, args[0])
            return {
                "success": bool(obj),
                "result": "success" if obj else "not_found",
                "answer": f"{args[0]} found." if obj else f"{args[0]} not found.",
                "evidence": _object_evidence(obj) if obj else [],
                "message": f"Symbolically checked {action}.",
            }

        if name == "answer_location" and args:
            status = evaluate_visual_task(f"Identify where the {args[0]} is.", self.world_model)
            return _from_task_status(status)

        if name == "answer_relation" and len(args) == 3:
            status = evaluate_visual_task(f"Is the {args[0]} {args[1]} the {args[2]}?", self.world_model)
            return _from_task_status(status)

        if name == "mark_task_complete":
            status = evaluate_visual_task(self.task, self.world_model)
            return _from_task_status(status)

        return {
            "success": False,
            "result": "unsupported_symbolic_action",
            "answer": "",
            "evidence": [],
            "message": f"{action} is not supported by SymbolicVisualExecutor.",
        }


def _from_task_status(status: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "success": bool(status.get("success")),
        "result": str(status.get("status", "in_progress")),
        "answer": str(status.get("answer", "")),
        "evidence": list(status.get("evidence", [])),
        "message": str(status.get("reason", "")),
    }


def _find_object(world_model: Dict[str, Any], name: str) -> Dict[str, Any] | None:
    normalized = _normalize(name)
    aliases = {"book": {"book", "notebook", "booklet", "magazine"}, "chair": {"chair", "armchair"}}
    candidates = aliases.get(normalized, {normalized})
    for obj in world_model.get("objects", []):
        if not isinstance(obj, dict):
            continue
        values = {_normalize(str(obj.get("name", ""))), _normalize(str(obj.get("id", "")))}
        if values & candidates:
            return obj
    return None


def _object_evidence(obj: Dict[str, Any]) -> list[str]:
    location = obj.get("location", {})
    evidence = [f"object={obj.get('name') or obj.get('id')}"]
    if isinstance(location, dict):
        evidence.append(f"room={location.get('room', '')}")
        evidence.append(f"support={location.get('support', '')}")
        evidence.append(f"confidence={location.get('confidence', '')}")
    return evidence


def _normalize(value: str) -> str:
    return value.strip().lower().replace(" ", "_")
