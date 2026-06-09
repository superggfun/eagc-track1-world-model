from typing import Any, Dict, Iterable, List


def apply_extraction(world_model: Dict[str, Any], extraction: Dict[str, Any]) -> Dict[str, Any]:
    for key in ["rooms", "objects", "relations", "states", "affordances", "uncertainty"]:
        world_model[key] = merge_unique(world_model.get(key, []), extraction.get(key, []))
    return world_model


def mark_object_location_unknown(
    world_model: Dict[str, Any], object_name: str, reason: str
) -> Dict[str, Any]:
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
