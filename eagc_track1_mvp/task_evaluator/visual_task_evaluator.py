from __future__ import annotations

import re
from typing import Any, Dict, List


RELATION_ALIASES = {
    "near": {"near", "beside", "next_to", "adjacent_to"},
    "beside": {"near", "beside", "next_to", "adjacent_to"},
    "on": {"on", "atop"},
    "inside": {"inside", "in"},
    "under": {"under", "below"},
}
OBJECT_ALIASES = {
    "book": ["book", "notebook", "booklet", "magazine"],
    "laptop": ["laptop", "computer"],
    "chair": ["chair", "armchair"],
    "bed": ["bed"],
}


def evaluate_visual_task(task: str, world_model: Dict[str, Any], confidence_threshold: float = 0.45) -> Dict[str, Any]:
    task_lower = task.lower().strip()
    relation_query = _parse_relation_query(task_lower)
    near_query = _parse_find_near(task_lower)
    identify = _parse_identify_location(task_lower)
    find = _parse_find_object(task_lower)

    if relation_query:
        subject, relation, target = relation_query
        return _evaluate_relation(world_model, subject, relation, target)
    if near_query:
        subject, target = near_query
        return _evaluate_relation(world_model, subject, "near", target)
    if identify:
        return _evaluate_location(world_model, identify, confidence_threshold)
    if find:
        return _evaluate_find(world_model, find, confidence_threshold)
    return _status(
        "in_progress",
        False,
        f"Unsupported visual task form: {task}",
        "The visual task evaluator could not classify this request.",
        [],
    )


def _evaluate_find(world_model: Dict[str, Any], object_name: str, confidence_threshold: float) -> Dict[str, Any]:
    obj = _find_object(world_model, object_name)
    if not obj:
        return _status("in_progress", False, f"{object_name} not found.", f"I do not see {object_name}.", [])
    confidence = _object_confidence(obj)
    evidence = [f"object={obj.get('name')}", f"confidence={confidence}"]
    if confidence >= confidence_threshold:
        return _status(
            "complete",
            True,
            f"{object_name} found as {obj.get('name')}.",
            f"Found {obj.get('name')} in the visual world model.",
            evidence,
        )
    return _status(
        "uncertain",
        False,
        f"{object_name} exists but confidence is low.",
        f"{object_name} may be present, but confidence is below threshold.",
        evidence,
    )


def _evaluate_location(world_model: Dict[str, Any], object_name: str, confidence_threshold: float) -> Dict[str, Any]:
    obj = _find_object(world_model, object_name)
    if not obj:
        return _status("in_progress", False, f"{object_name} not found.", f"I cannot identify where {object_name} is.", [])
    location = obj.get("location", {})
    if not isinstance(location, dict):
        location = {}
    support = str(location.get("support") or "")
    room = str(location.get("room") or "")
    status = str(location.get("status") or "")
    confidence = float(location.get("confidence", _object_confidence(obj)))
    active_relation = _best_location_relation(world_model, str(obj.get("name") or object_name))
    evidence = [
        f"object={obj.get('name')}",
        f"location.status={status}",
        f"room={room or 'unknown'}",
        f"support={support or 'unknown'}",
        f"confidence={confidence}",
    ]
    if active_relation:
        evidence.append(
            f"relation={active_relation.get('subject')} {active_relation.get('relation')} {active_relation.get('object')}"
        )
    if (support or room or active_relation) and status != "unknown" and confidence >= confidence_threshold:
        answer = _location_answer(str(obj.get("name") or object_name), room, support, active_relation)
        return _status("complete", True, answer, answer, evidence)
    return _status(
        "uncertain",
        False,
        f"{object_name} location is uncertain.",
        f"I found {obj.get('name')}, but its location is uncertain.",
        evidence,
    )


def _evaluate_relation(world_model: Dict[str, Any], subject: str, relation: str, target: str) -> Dict[str, Any]:
    subject_obj = _find_object(world_model, subject)
    target_obj = _find_object(world_model, target)
    if not subject_obj or not target_obj:
        missing = [name for name, obj in [(subject, subject_obj), (target, target_obj)] if not obj]
        return _status(
            "in_progress",
            False,
            f"Missing objects: {', '.join(missing)}.",
            f"I cannot answer because {', '.join(missing)} is not in the visual world model.",
            [],
        )
    subject_name = str(subject_obj.get("name") or subject)
    target_name = str(target_obj.get("name") or target)
    matched = _find_relation(world_model, subject_name, relation, target_name)
    if not matched:
        matched = _relation_from_location(subject_obj, subject_name, relation, target_name)
    if matched:
        evidence = [
            f"relation={matched.get('subject')} {matched.get('relation')} {matched.get('object')}",
            f"status={matched.get('status')}",
            f"confidence={matched.get('confidence')}",
        ]
        if matched.get("status") in {"active", "inferred"} and float(matched.get("confidence", 0.0)) >= 0.45:
            answer = f"Yes, {subject_name} is {matched.get('relation')} {target_name}."
            return _status("complete", True, answer, answer, evidence)
        return _status(
            "uncertain",
            False,
            f"Relation is {matched.get('status')}.",
            f"The relation between {subject_name} and {target_name} is uncertain or stale.",
            evidence,
        )
    return _status(
        "uncertain",
        False,
        f"No active relation found for {subject} {relation} {target}.",
        f"I found both objects, but not a reliable {relation} relation.",
        [f"subject={subject_name}", f"target={target_name}"],
    )


def _status(status: str, success: bool, reason: str, answer: str, evidence: List[str]) -> Dict[str, Any]:
    return {
        "status": status,
        "success": success,
        "reason": reason,
        "answer": answer,
        "evidence": evidence,
    }


def _parse_find_object(task_lower: str) -> str:
    match = re.search(r"\bfind (?:the )?([a-z0-9_ ]+?)(?:\.|$)", task_lower)
    if not match:
        return ""
    text = match.group(1).strip()
    if " near " in text:
        return ""
    return _normalize_object(text)


def _parse_identify_location(task_lower: str) -> str:
    match = re.search(r"\b(?:identify|find) where (?:the )?([a-z0-9_ ]+?) is\b", task_lower)
    return _normalize_object(match.group(1)) if match else ""


def _parse_relation_query(task_lower: str) -> tuple[str, str, str] | None:
    match = re.search(r"\bis (?:the )?([a-z0-9_ ]+?) (on|inside|in|under|near|beside) (?:the )?([a-z0-9_ ]+?)\?", task_lower)
    if not match:
        return None
    return _normalize_object(match.group(1)), _normalize_relation(match.group(2)), _normalize_object(match.group(3))


def _parse_find_near(task_lower: str) -> tuple[str, str] | None:
    match = re.search(r"\bfind (?:the )?([a-z0-9_ ]+?) (?:near|beside) (?:the )?([a-z0-9_ ]+?)(?:\.|$)", task_lower)
    if not match:
        return None
    return _normalize_object(match.group(1)), _normalize_object(match.group(2))


def _normalize_object(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", text.strip().lower()).strip("_")


def _normalize_relation(text: str) -> str:
    return "inside" if text == "in" else text


def _find_object(world_model: Dict[str, Any], object_name: str) -> Dict[str, Any] | None:
    candidates = OBJECT_ALIASES.get(object_name, [object_name])
    normalized_candidates = {_normalize_object(candidate) for candidate in candidates}
    for obj in world_model.get("objects", []):
        if not isinstance(obj, dict):
            continue
        values = {_normalize_object(str(obj.get("name") or "")), _normalize_object(str(obj.get("id") or ""))}
        if values & normalized_candidates:
            return obj
    return None


def _object_confidence(obj: Dict[str, Any]) -> float:
    location = obj.get("location")
    if isinstance(location, dict) and location.get("confidence") is not None:
        return float(location.get("confidence", 0.0))
    return float(obj.get("confidence", 0.5))


def _best_location_relation(world_model: Dict[str, Any], subject: str) -> Dict[str, Any] | None:
    for relation in world_model.get("relations", []):
        if not isinstance(relation, dict):
            continue
        if relation.get("subject") == subject and relation.get("status") in {"active", "inferred"}:
            return relation
    return None


def _find_relation(world_model: Dict[str, Any], subject: str, relation_name: str, target: str) -> Dict[str, Any] | None:
    accepted_relations = RELATION_ALIASES.get(relation_name, {relation_name})
    target_aliases = {_normalize_object(value) for value in OBJECT_ALIASES.get(target, [target])}
    subject_aliases = {_normalize_object(value) for value in OBJECT_ALIASES.get(subject, [subject])}
    best_stale = None
    for relation in world_model.get("relations", []):
        if not isinstance(relation, dict):
            continue
        rel_subject = _normalize_object(str(relation.get("subject", "")))
        rel_object = _normalize_object(str(relation.get("object", "")))
        if not _matches_alias(rel_subject, subject_aliases) or not _matches_alias(rel_object, target_aliases):
            continue
        if relation.get("relation") not in accepted_relations:
            continue
        if relation.get("status") in {"active", "inferred"}:
            return relation
        best_stale = best_stale or relation
    return best_stale


def _relation_from_location(
    subject_obj: Dict[str, Any],
    subject_name: str,
    relation_name: str,
    target_name: str,
) -> Dict[str, Any] | None:
    location = subject_obj.get("location", {})
    if not isinstance(location, dict):
        return None
    support = _normalize_object(str(location.get("support", "")))
    target_aliases = {_normalize_object(value) for value in OBJECT_ALIASES.get(target_name, [target_name])}
    if relation_name == "on" and _matches_alias(support, target_aliases):
        return {
            "subject": subject_name,
            "relation": "on",
            "object": target_name,
            "status": location.get("status", "active") if location.get("status") != "unknown" else "uncertain",
            "confidence": float(location.get("confidence", 0.5)),
        }
    return None


def _matches_alias(value: str, aliases: set[str]) -> bool:
    if value in aliases:
        return True
    return any(alias and (value.endswith(alias) or alias in value.split("_")) for alias in aliases)


def _location_answer(
    object_name: str,
    room: str,
    support: str,
    relation: Dict[str, Any] | None,
) -> str:
    if relation:
        return f"{object_name} is {relation.get('relation')} {relation.get('object')}."
    if support:
        return f"{object_name} is on or near {support}."
    if room:
        return f"{object_name} is in {room}."
    return f"{object_name} location is unknown."
