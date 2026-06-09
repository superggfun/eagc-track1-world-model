import re
from typing import Any, Dict, Iterable, List


def apply_extraction(world_model: Dict[str, Any], extraction: Dict[str, Any]) -> Dict[str, Any]:
    world_model["rooms"] = merge_unique(world_model.get("rooms", []), extraction.get("rooms", []))
    world_model["objects"] = upsert_objects(world_model.get("objects", []), extraction.get("objects", []))
    world_model["relations"] = upsert_relations(
        world_model.get("relations", []), extraction.get("relations", [])
    )
    world_model["states"] = upsert_states(world_model.get("states", []), extraction.get("states", []))
    world_model["affordances"] = merge_affordances(
        world_model.get("affordances", []), extraction.get("affordances", [])
    )
    world_model["uncertainty"] = merge_unique(
        world_model.get("uncertainty", []), extraction.get("uncertainty", [])
    )
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
        if hint.get("category"):
            obj["category"] = hint["category"]
        support = location.get("support")
        if support and location.get("status") != "unknown":
            _ensure_support_object(world_model, str(support), current_room)
            _reconcile_support_relation(world_model, str(obj.get("name")), str(support))

    known_names = {
        obj.get("name")
        for obj in world_model.get("objects", [])
        if isinstance(obj, dict) and obj.get("name")
    }
    for name, hint in object_hints.items():
        if name in known_names:
            continue
        status = hint.get("status", "inferred")
        upsert_object(
            world_model,
            {
                "id": slug(name),
                "name": name,
                "category": hint.get("category", "inferred_support"),
                "location": {
                    "room": current_room if status != "unknown" else "",
                    "region": hint.get("region", ""),
                    "support": hint.get("support", ""),
                    "status": status,
                    "confidence": float(hint.get("confidence", 0.5)),
                },
                "state": hint.get("state", "inferred"),
            },
        )
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


def upsert_object(world_model: Dict[str, Any], obj: Dict[str, Any]) -> Dict[str, Any]:
    world_model["objects"] = upsert_objects(world_model.get("objects", []), [obj])
    return world_model


def upsert_state(world_model: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    world_model["states"] = upsert_states(world_model.get("states", []), [state])
    return world_model


def upsert_relation(world_model: Dict[str, Any], relation: Dict[str, Any]) -> Dict[str, Any]:
    world_model["relations"] = upsert_relations(world_model.get("relations", []), [relation])
    return world_model


def remove_state(
    world_model: Dict[str, Any], entity: str, attribute: str, value: Any | None = None
) -> Dict[str, Any]:
    world_model["states"] = [
        state
        for state in world_model.get("states", [])
        if not (
            isinstance(state, dict)
            and state.get("entity") == entity
            and state.get("attribute") == attribute
            and (value is None or state.get("value") == value)
        )
    ]
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
    upsert_state(world_model, {"entity": object_name, "attribute": "location", "value": "unknown"})
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


def active_location_relations(world_model: Dict[str, Any], object_name: str) -> List[Dict[str, Any]]:
    location_relations = {"on", "inside", "under", "near", "beside", "at"}
    return [
        relation
        for relation in world_model.get("relations", [])
        if isinstance(relation, dict)
        and relation.get("subject") == object_name
        and relation.get("relation") in location_relations
        and relation.get("status") == "active"
    ]


def merge_unique(existing: List[Any], incoming: Iterable[Any]) -> List[Any]:
    merged = list(existing)
    fingerprints = {_fingerprint(item) for item in merged}
    for item in incoming:
        fingerprint = _fingerprint(item)
        if fingerprint not in fingerprints:
            merged.append(item)
            fingerprints.add(fingerprint)
    return merged


def upsert_objects(existing: List[Any], incoming: Iterable[Any]) -> List[Any]:
    merged = [item for item in existing if isinstance(item, dict)]
    for item in incoming:
        if not isinstance(item, dict):
            continue
        key = _object_key(item)
        for index, current in enumerate(merged):
            if _object_key(current) == key:
                merged[index] = {**current, **item}
                break
        else:
            merged.append(dict(item))
    return merged


def upsert_states(existing: List[Any], incoming: Iterable[Any]) -> List[Any]:
    merged = [item for item in existing if isinstance(item, dict)]
    for item in incoming:
        if not isinstance(item, dict):
            continue
        key = (item.get("entity"), item.get("attribute"))
        for index, current in enumerate(merged):
            if (current.get("entity"), current.get("attribute")) == key:
                merged[index] = {**current, **item}
                break
        else:
            merged.append(dict(item))
    return merged


def upsert_relations(existing: List[Any], incoming: Iterable[Any]) -> List[Any]:
    merged = [item for item in existing if isinstance(item, dict)]
    for item in incoming:
        if not isinstance(item, dict):
            continue
        key = (item.get("subject"), item.get("relation"), item.get("object"))
        for index, current in enumerate(merged):
            if (current.get("subject"), current.get("relation"), current.get("object")) == key:
                merged[index] = {**current, **item}
                break
        else:
            merged.append(dict(item))
    return merged


def merge_affordances(existing: List[Any], incoming: Iterable[Any]) -> List[Any]:
    merged = [item for item in existing if isinstance(item, dict)]
    for item in incoming:
        if not isinstance(item, dict):
            continue
        obj = item.get("object")
        actions = list(item.get("actions", [])) if isinstance(item.get("actions"), list) else []
        for current in merged:
            if current.get("object") == obj:
                current_actions = current.setdefault("actions", [])
                for action in actions:
                    if action not in current_actions:
                        current_actions.append(action)
                break
        else:
            merged.append({"object": obj, "actions": actions})
    return merged


def _fingerprint(item: Any) -> str:
    if isinstance(item, dict):
        return repr(sorted(item.items()))
    return repr(item)


def _object_key(obj: Dict[str, Any]) -> str:
    return str(obj.get("id") or obj.get("name") or slug(str(obj)))


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


def _ensure_support_object(world_model: Dict[str, Any], support: str, room: str) -> None:
    if any(
        isinstance(obj, dict) and (obj.get("name") == support or obj.get("id") == support)
        for obj in world_model.get("objects", [])
    ):
        return
    upsert_object(
        world_model,
        {
            "id": slug(support),
            "name": support,
            "category": "inferred_support",
            "location": {
                "room": room,
                "region": "inferred_area",
                "support": "",
                "status": "inferred",
                "confidence": 0.5,
            },
            "state": "inferred",
        },
    )


def _reconcile_support_relation(world_model: Dict[str, Any], object_name: str, support: str) -> None:
    if any(
        relation.get("subject") == object_name
        and relation.get("relation") == "on"
        and relation.get("object") == support
        and relation.get("status") == "active"
        for relation in world_model.get("relations", [])
        if isinstance(relation, dict)
    ):
        return
    stale_location_relations(world_model, object_name)
    upsert_relation(
        world_model,
        {
            "subject": object_name,
            "relation": "on",
            "object": support,
            "status": "active",
            "confidence": 0.85,
            "observed_at_step": 1,
        },
    )
