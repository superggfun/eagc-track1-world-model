from typing import Any, Dict

from planner.action_schema import parse_action
from world_model.update import remove_state, stale_location_relations, upsert_relation, upsert_state


def apply_action_effect(
    world_model: Dict[str, Any], action: str, result: Dict[str, Any], step: int
) -> Dict[str, Any]:
    if not result.get("success", False):
        return world_model

    action_name, args = parse_action(action)
    if action_name == "pick_up" and len(args) == 1:
        _apply_pick_up(world_model, args[0])
    elif action_name == "place_on" and len(args) == 2:
        _apply_place_on(world_model, args[0], args[1], step)
    elif action_name == "open" and len(args) == 1:
        upsert_state(world_model, {"entity": args[0], "attribute": "status", "value": "open"})
    elif action_name == "unlock" and len(args) == 1:
        upsert_state(world_model, {"entity": args[0], "attribute": "lock_state", "value": "unlocked"})
    elif action_name == "close" and len(args) == 1:
        upsert_state(world_model, {"entity": args[0], "attribute": "status", "value": "closed"})
    elif action_name == "navigate_to" and len(args) == 1:
        _apply_navigation(world_model, args[0])
    elif action_name == "enter" and len(args) == 1:
        _apply_navigation(world_model, args[0])
    elif action_name == "substitute_tool" and len(args) == 2:
        upsert_state(world_model, {"entity": "task", "attribute": "active_tool", "value": args[1]})
        upsert_state(
            world_model,
            {"entity": "task", "attribute": "substituted", "value": f"{args[0]}->{args[1]}"},
        )
    elif action_name == "use_tool" and len(args) == 2:
        _apply_use_tool(world_model, args[0], args[1])
    return world_model


def apply_exception_effect(
    world_model: Dict[str, Any], failure: Dict[str, Any], step: int
) -> Dict[str, Any]:
    exception = failure.get("exception", {})
    exception_type = exception.get("type")
    obj = exception.get("object")
    message = failure.get("message", "")

    if exception_type == "door_locked" and obj:
        upsert_state(world_model, {"entity": obj, "attribute": "observed_lock_state", "value": "locked"})
        upsert_state(world_model, {"entity": obj, "attribute": "lock_state", "value": "locked"})
        upsert_state(world_model, {"entity": obj, "attribute": "status", "value": "locked"})
        world_model.setdefault("uncertainty", []).append(
            {"item": obj, "reason": message or "Door is locked.", "level": "medium"}
        )
    elif exception_type == "target_container_unavailable" and obj:
        upsert_state(world_model, {"entity": obj, "attribute": "availability", "value": "unavailable"})
        world_model.setdefault("uncertainty", []).append(
            {"item": obj, "reason": message or "Target container unavailable.", "level": "high"}
        )
    elif exception_type == "tool_substitution":
        substitute = exception.get("substitute")
        upsert_state(world_model, {"entity": "task", "attribute": "required_tool", "value": obj})
        upsert_state(world_model, {"entity": "task", "attribute": "substitute_tool", "value": substitute})
        upsert_state(
            world_model,
            {
                "entity": "task",
                "attribute": "substitution_reason",
                "value": message or f"{obj} unavailable; use {substitute}.",
            },
        )
        world_model.setdefault("uncertainty", []).append(
            {"item": obj, "reason": message or "Tool substitution required.", "level": "medium"}
        )
    return world_model


def _apply_pick_up(world_model: Dict[str, Any], obj_name: str) -> None:
    stale_location_relations(world_model, obj_name)
    agent_state = world_model.setdefault("agent_state", {})
    agent_state["holding"] = obj_name
    obj = _find_object(world_model, obj_name)
    if obj is None:
        return
    location = _location_for_agent_hand(world_model)
    obj["location"] = location
    obj["state"] = "held"
    upsert_state(world_model, {"entity": obj_name, "attribute": "held_by", "value": "agent"})


def _apply_place_on(world_model: Dict[str, Any], obj_name: str, target: str, step: int) -> None:
    stale_location_relations(world_model, obj_name)
    agent_state = world_model.setdefault("agent_state", {})
    if agent_state.get("holding") == obj_name:
        agent_state["holding"] = None
    obj = _find_object(world_model, obj_name)
    if obj is not None:
        current_room = agent_state.get("current_room", "")
        obj["location"] = {
            "room": current_room,
            "region": _region_for_object(world_model, target),
            "support": target,
            "status": "known",
            "confidence": 0.9,
        }
        obj["state"] = "placed"
    upsert_relation(
        world_model,
        {
            "subject": obj_name,
            "relation": "on",
            "object": target,
            "status": "active",
            "confidence": 0.9,
            "observed_at_step": step,
        },
    )
    remove_state(world_model, obj_name, "held_by", "agent")
    upsert_state(world_model, {"entity": obj_name, "attribute": "location", "value": target})


def _apply_navigation(world_model: Dict[str, Any], target: str) -> None:
    if target == "door":
        upsert_state(world_model, {"entity": "agent", "attribute": "near", "value": "door"})
        return
    world_model.setdefault("agent_state", {})["current_room"] = target
    upsert_state(world_model, {"entity": "agent", "attribute": "location", "value": target})
    if target == "next_room":
        upsert_state(world_model, {"entity": "agent", "attribute": "entered", "value": "next_room"})


def _apply_use_tool(world_model: Dict[str, Any], tool: str, target: str) -> None:
    upsert_state(world_model, {"entity": target, "attribute": "status", "value": "completed_or_modified"})
    if target == "loose_screw" and tool == "coin":
        upsert_state(world_model, {"entity": "loose_screw", "attribute": "tightened_by", "value": "coin"})
        upsert_state(world_model, {"entity": "loose_screw", "attribute": "status", "value": "tightened"})


def _find_object(world_model: Dict[str, Any], name: str) -> Dict[str, Any] | None:
    for obj in world_model.get("objects", []):
        if isinstance(obj, dict) and (obj.get("name") == name or obj.get("id") == name):
            return obj
    return None


def _location_for_agent_hand(world_model: Dict[str, Any]) -> Dict[str, Any]:
    current_room = world_model.get("agent_state", {}).get("current_room", "")
    return {
        "room": current_room,
        "region": "agent",
        "support": "agent_hand",
        "status": "known",
        "confidence": 1.0,
    }


def _region_for_object(world_model: Dict[str, Any], name: str) -> str:
    obj = _find_object(world_model, name)
    if obj and isinstance(obj.get("location"), dict):
        return str(obj["location"].get("region") or "visible_area")
    return "visible_area"
