import re
from typing import Any, Dict, Iterable, List

LOCATION_RELATIONS = {"on", "inside", "under", "near", "beside", "at"}


def _relation_key(relation: Dict[str, Any]) -> tuple:
    return (relation.get("subject"), relation.get("relation"), relation.get("object"))


def _state_key(state: Dict[str, Any]) -> tuple:
    return (state.get("entity"), state.get("attribute"))


def _topology_key(node: Dict[str, Any]) -> str:
    return node.get("room", "")


def _frontier_key(item: Dict[str, Any]) -> tuple:
    return (item.get("target"), item.get("via"))


def _is_active_location_relation(relation: Dict[str, Any]) -> bool:
    return (
        relation.get("status") == "active"
        and relation.get("relation") in LOCATION_RELATIONS
    )


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
    _normalize_held_object(world_model)
    return world_model


def apply_frame_visibility(
    world_model: Dict[str, Any],
    observed_names: Iterable[str],
    frame_step: int,
) -> Dict[str, Any]:
    observed = {str(name) for name in observed_names if name}
    visibility_states: list[dict] = []
    uncertainty_items: list[dict] = []
    for obj in world_model.get("objects", []):
        if not isinstance(obj, dict):
            continue
        name = str(obj.get("name") or obj.get("id") or "")
        if not name:
            continue
        if name in observed or str(obj.get("id", "")) in observed:
            obj["visibility"] = "observed_current_frame"
            obj["last_observed_step"] = frame_step
            location = obj.get("location")
            if isinstance(location, dict):
                confidence = float(location.get("confidence", 0.75))
                location["confidence"] = round(min(1.0, max(confidence, confidence + 0.05)), 4)
            visibility_states.append(
                {"entity": name, "attribute": "visibility", "value": "observed_current_frame"}
            )
            continue
        obj["visibility"] = "not_observed_current_frame"
        location = obj.get("location")
        if isinstance(location, dict):
            confidence = float(location.get("confidence", 0.5))
            location["confidence"] = round(max(0.1, confidence * 0.85), 4)
        visibility_states.append(
            {"entity": name, "attribute": "visibility", "value": "not_observed_current_frame"}
        )
        uncertainty_items.append(
            {
                "item": name,
                "reason": f"Object not visible in current frame {frame_step}; retained from prior frames.",
                "level": "medium",
            }
        )
    if visibility_states:
        world_model["states"] = upsert_states(world_model.get("states", []), visibility_states)
    if uncertainty_items:
        world_model.setdefault("uncertainty", []).extend(uncertainty_items)
    return world_model


def apply_environment_context(world_model: Dict[str, Any], env_packet: Dict[str, Any]) -> Dict[str, Any]:
    current_room = env_packet.get("current_room") or env_packet.get("room") or "unknown"
    packet_agent_state = env_packet.get("agent_state", {})
    if not isinstance(packet_agent_state, dict):
        packet_agent_state = {}
    existing_agent_state = world_model.get("agent_state", {})
    world_model["agent_state"] = {
        **existing_agent_state,
        "current_room": current_room,
        "holding": packet_agent_state.get("holding", existing_agent_state.get("holding")),
        "step": packet_agent_state.get("step", existing_agent_state.get("step", 0)),
        "last_action": existing_agent_state.get("last_action", ""),
        "mode": "observing",
    }
    topology = env_packet.get("topology") or [
        {"room": current_room, "node_type": "room", "visited": True, "frontiers": []}
    ]
    world_model["topology"] = upsert_topology(world_model.get("topology", []), topology)
    visited_rooms = list(packet_agent_state.get("visited_rooms", []))
    if not visited_rooms:
        visited_rooms = [
            node.get("room")
            for node in topology
            if isinstance(node, dict) and node.get("visited") is True and node.get("room")
        ]
    if visited_rooms:
        world_model["visited_rooms"] = merge_unique(world_model.get("visited_rooms", []), visited_rooms)
    frontiers = env_packet.get("visible_frontiers") or packet_agent_state.get("known_frontiers", [])
    if frontiers:
        world_model["frontiers"] = merge_unique(world_model.get("frontiers", []), frontiers)

    if env_packet.get("generated_episode"):
        world_model["generated_episode"] = True

    object_hints = env_packet.get("object_hints", {})

    # Build lightweight O(1) lookup indices to avoid linear scans inside the
    # per-object loop (_ensure_support_object / _reconcile_support_relation).
    object_identity_index: set[str] = set()
    for obj in world_model.get("objects", []):
        if isinstance(obj, dict):
            name = obj.get("name")
            obj_id = obj.get("id")
            if name:
                object_identity_index.add(name)
            if obj_id:
                object_identity_index.add(obj_id)

    active_relation_index: set[tuple] = set()
    for rel in world_model.get("relations", []):
        if isinstance(rel, dict) and rel.get("status") == "active":
            active_relation_index.add(
                (rel.get("subject"), rel.get("relation"), rel.get("object"))
            )

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
            _ensure_support_object(world_model, str(support), current_room, object_identity_index)
            _reconcile_support_relation(world_model, str(obj.get("name")), str(support), active_relation_index)

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
    _normalize_held_object(world_model)
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


def merge_unique(existing: List[Any], incoming: Iterable[Any], key=None) -> List[Any]:
    merged = list(existing)
    _fp = key if key is not None else _fingerprint
    fingerprints: set[Any] = {_fp(item) for item in merged}
    for item in incoming:
        fingerprint = _fp(item)
        if fingerprint not in fingerprints:
            merged.append(item)
            fingerprints.add(fingerprint)
    return merged


def upsert_topology(existing: List[Any], incoming: Iterable[Any]) -> List[Any]:
    merged = [dict(item) for item in existing if isinstance(item, dict)]
    index: Dict[str, int] = {_topology_key(node): i for i, node in enumerate(merged)}
    for item in incoming:
        if not isinstance(item, dict):
            continue
        room = item.get("room")
        if not room:
            continue
        incoming_node = dict(item)
        incoming_frontiers = incoming_node.get("frontiers", [])
        if not isinstance(incoming_frontiers, list):
            incoming_frontiers = []
        if room in index:
            current = merged[index[room]]
            current_frontiers = current.get("frontiers", [])
            if not isinstance(current_frontiers, list):
                current_frontiers = []
            merged[index[room]] = {
                **current,
                **incoming_node,
                "visited": bool(current.get("visited")) or bool(incoming_node.get("visited")),
                "frontiers": _merge_frontiers(current_frontiers, incoming_frontiers),
            }
        else:
            if not isinstance(incoming_node.get("frontiers", []), list):
                incoming_node["frontiers"] = []
            index[room] = len(merged)
            merged.append(incoming_node)
    return merged


def _merge_frontiers(existing: List[Any], incoming: List[Any]) -> List[Any]:
    merged = [item for item in existing if isinstance(item, dict)]
    index: Dict[tuple, int] = {_frontier_key(item): i for i, item in enumerate(merged)}
    for item in incoming:
        if not isinstance(item, dict):
            continue
        key = _frontier_key(item)
        if key in index:
            merged[index[key]] = {**merged[index[key]], **item}
        else:
            index[key] = len(merged)
            merged.append(dict(item))
    return merged


def upsert_objects(existing: List[Any], incoming: Iterable[Any]) -> List[Any]:
    merged = [item for item in existing if isinstance(item, dict)]
    index: Dict[str, int] = {_object_key(item): i for i, item in enumerate(merged)}
    for item in incoming:
        if not isinstance(item, dict):
            continue
        key = _object_key(item)
        if key in index:
            merged[index[key]] = {**merged[index[key]], **item}
        else:
            index[key] = len(merged)
            merged.append(dict(item))
    return merged


def upsert_states(existing: List[Any], incoming: Iterable[Any]) -> List[Any]:
    merged = [item for item in existing if isinstance(item, dict)]
    index: Dict[tuple, int] = {_state_key(item): i for i, item in enumerate(merged)}
    for item in incoming:
        if not isinstance(item, dict):
            continue
        key = _state_key(item)
        if key in index:
            merged[index[key]] = {**merged[index[key]], **item}
        else:
            index[key] = len(merged)
            merged.append(dict(item))
    return merged


def upsert_relations(existing: List[Any], incoming: Iterable[Any]) -> List[Any]:
    merged = [item for item in existing if isinstance(item, dict)]
    # O(1) index: relation key -> position in merged
    relation_index: Dict[tuple, int] = {
        _relation_key(item): i for i, item in enumerate(merged)
    }
    # Subject -> set of positions for active location relations (for fast stale)
    active_location_by_subject: Dict[Any, set] = {}
    for i, rel in enumerate(merged):
        if _is_active_location_relation(rel):
            subject = rel.get("subject")
            active_location_by_subject.setdefault(subject, set()).add(i)

    for item in incoming:
        if not isinstance(item, dict):
            continue
        incoming_key = _relation_key(item)

        # Stale only same-subject active location relations (O(1) lookup)
        if _is_active_location_relation(item):
            subject = item.get("subject")
            to_stale = active_location_by_subject.get(subject, set())
            for stale_idx in list(to_stale):
                stale_rel = merged[stale_idx]
                if _relation_key(stale_rel) == incoming_key:
                    continue  # never stale the same-key relation
                stale_rel["status"] = "stale"
                stale_rel["confidence"] = min(float(stale_rel.get("confidence", 0.5)), 0.2)
                to_stale.discard(stale_idx)

        # Upsert by relation key
        pos = relation_index.get(incoming_key)
        if pos is not None:
            old_rel = merged[pos]
            was_active_loc = _is_active_location_relation(old_rel)
            merged[pos] = {**old_rel, **item}
            # Maintain active location index
            if was_active_loc and not _is_active_location_relation(merged[pos]):
                subj = old_rel.get("subject")
                active_location_by_subject.get(subj, set()).discard(pos)
            elif not was_active_loc and _is_active_location_relation(merged[pos]):
                subj = merged[pos].get("subject")
                active_location_by_subject.setdefault(subj, set()).add(pos)
        else:
            new_pos = len(merged)
            merged.append(dict(item))
            relation_index[incoming_key] = new_pos
            if _is_active_location_relation(item):
                subject = item.get("subject")
                active_location_by_subject.setdefault(subject, set()).add(new_pos)

    return merged


def merge_affordances(existing: List[Any], incoming: Iterable[Any]) -> List[Any]:
    merged = [item for item in existing if isinstance(item, dict)]
    # O(1) index: object name -> position
    index: Dict[str, int] = {
        item.get("object", ""): i
        for i, item in enumerate(merged)
        if isinstance(item, dict) and item.get("object")
    }
    for item in incoming:
        if not isinstance(item, dict):
            continue
        obj = item.get("object")
        actions = list(item.get("actions", [])) if isinstance(item.get("actions"), list) else []
        if obj and obj in index:
            current = merged[index[obj]]
            current_actions = current.setdefault("actions", [])
            for action in actions:
                if action not in current_actions:
                    current_actions.append(action)
        else:
            new_pos = len(merged)
            merged.append({"object": obj, "actions": actions})
            if obj:
                index[obj] = new_pos
    return merged


def _freeze_for_fingerprint(value: Any) -> Any:
    """Recursively convert a value into a hashable form for fingerprinting.

    Handles nested dicts, lists, and sets that frozenset alone cannot."""
    if isinstance(value, dict):
        return tuple(sorted((k, _freeze_for_fingerprint(v)) for k, v in value.items()))
    if isinstance(value, list):
        return tuple(_freeze_for_fingerprint(v) for v in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze_for_fingerprint(v) for v in value))
    return value


def _fingerprint(item: Any) -> Any:
    return _freeze_for_fingerprint(item)


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


def _normalize_held_object(world_model: Dict[str, Any]) -> None:
    agent_state = world_model.get("agent_state", {})
    if not isinstance(agent_state, dict):
        return
    holding = agent_state.get("holding")
    if not holding:
        return
    current_room = str(agent_state.get("current_room") or "")
    holding_name = str(holding)
    identity_index: set[str] = set()
    for obj in world_model.get("objects", []):
        if isinstance(obj, dict):
            name, oid = obj.get("name"), obj.get("id")
            if name:
                identity_index.add(name)
            if oid:
                identity_index.add(oid)
        if obj.get("name") != holding_name and obj.get("id") != holding_name:
            continue
        obj["location"] = {
            "room": current_room,
            "region": "agent",
            "support": "agent_hand",
            "status": "known",
            "confidence": 1.0,
        }
        if obj.get("category") in {"container", "surface", "furniture", "door", "room"}:
            obj["category"] = "object"
        obj["state"] = "held"
        upsert_state(world_model, {"entity": holding_name, "attribute": "held_by", "value": "agent"})
        _ensure_support_object(world_model, "agent_hand", current_room, identity_index)
        return


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "unknown_object"


def _ensure_support_object(
    world_model: Dict[str, Any],
    support: str,
    room: str,
    object_identity_index: set[str] | None = None,
) -> None:
    if object_identity_index is not None:
        if support in object_identity_index:
            return
    elif any(
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
    # Keep the index in sync so subsequent calls see the new object
    if object_identity_index is not None:
        object_identity_index.add(support)
        object_identity_index.add(slug(support))


def _reconcile_support_relation(
    world_model: Dict[str, Any],
    object_name: str,
    support: str,
    active_relation_index: set[tuple] | None = None,
) -> None:
    relation_key = (object_name, "on", support)
    if active_relation_index is not None:
        if relation_key in active_relation_index:
            return
    elif any(
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
    # Keep the index in sync for subsequent calls
    if active_relation_index is not None:
        active_relation_index.add(relation_key)
