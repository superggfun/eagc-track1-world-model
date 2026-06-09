import re
from typing import Any, Dict, Iterable, List


def apply_extraction(world_model: Dict[str, Any], extraction: Dict[str, Any]) -> Dict[str, Any]:
    for key in ["rooms", "objects", "relations", "states", "affordances", "uncertainty"]:
        world_model[key] = merge_unique(world_model.get(key, []), extraction.get(key, []))
    return world_model


def apply_environment_context(world_model: Dict[str, Any], env_packet: Dict[str, Any]) -> Dict[str, Any]:
    current_room = env_packet.get("current_room") or env_packet.get("room") or "unknown"
    world_model["agent_state"] = {
        **world_model.get("agent_state", {}),
        "current_room": current_room,
        "holding": world_model.get("agent_state", {}).get("holding"),
        "step": world_model.get("agent_state", {}).get("step", 0),
        "last_action": world_model.get("agent_state", {}).get("last_action", ""),
        "mode": "observing",
    }
    topology = env_packet.get("topology") or [
        {"room": current_room, "node_type": "room", "visited": True, "frontiers": []}
    ]
    world_model["topology"] = topology

    object_hints = env_packet.get("object_hints", {})
    for obj in world_model.get("objects", []):
        if not isinstance(obj, dict):
            continue
        hint = object_hints.get(obj.get("name"), {})
        location = obj.get("location")
        if not isinstance(location, dict):
            location = _known_location(current_room)
        location["room"] = location.get("room") or current_room
        location["region"] = hint.get("region") or location.get("region") or "visible_area"
        location["support"] = hint.get("support", location.get("support", ""))
        location["status"] = location.get("status") or "known"
        location["confidence"] = float(hint.get("confidence", location.get("confidence", 0.75)))
        obj["location"] = location
    return world_model


def update_agent_state(
    world_model: Dict[str, Any], step: int, last_action: str, mode: str, result: str = ""
) -> Dict[str, Any]:
    state = world_model.setdefault("agent_state", {})
    state["step"] = step
    state["last_action"] = last_action
    state["mode"] = mode
    if last_action.startswith("pick_up(") and result == "success":
        state["holding"] = last_action.removeprefix("pick_up(").removesuffix(")")
    return world_model


def mark_object_location_unknown(
    world_model: Dict[str, Any], object_name: str, reason: str
) -> Dict[str, Any]:
    for obj in world_model.get("objects", []):
        if isinstance(obj, dict) and obj.get("name") == object_name:
            obj["location"] = {
                "room": "",
                "region": "",
                "support": "",
                "status": "unknown",
                "confidence": 0.0,
            }
            obj["state"] = "location_unknown"

    stale_location_relations(world_model, object_name)

    world_model["states"] = [
        state
        for state in world_model.get("states", [])
        if not (state.get("entity") == object_name and state.get("attribute") == "location")
    ]
    world_model.setdefault("states", []).append(
        {"entity": object_name, "attribute": "location", "value": "unknown"}
    )
    world_model.setdefault("uncertainty", []).append(
        {"item": object_name, "reason": reason, "level": "high"}
    )
    return world_model


def stale_location_relations(world_model: Dict[str, Any], object_name: str) -> None:
    location_relations = {"on", "inside", "under", "near", "beside", "at"}
    for relation in world_model.get("relations", []):
        if not isinstance(relation, dict):
            continue
        if relation.get("subject") == object_name and relation.get("relation") in location_relations:
            relation["status"] = "stale"
            relation["confidence"] = min(float(relation.get("confidence", 0.5)), 0.2)


def merge_unique(existing: List[Any], incoming: Iterable[Any]) -> List[Any]:
    merged = list(existing)
    fingerprints = {_fingerprint(item) for item in merged}
    for item in incoming:
        fingerprint = _fingerprint(item)
        if fingerprint not in fingerprints:
            merged.append(item)
            fingerprints.add(fingerprint)
    return merged


def _fingerprint(item: Any) -> str:
    if isinstance(item, dict):
        return repr(sorted(item.items()))
    return repr(item)


def _known_location(room: str) -> Dict[str, Any]:
    return {
        "room": room,
        "region": "visible_area",
        "support": "",
        "status": "known",
        "confidence": 0.75,
    }


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "unknown_object"
