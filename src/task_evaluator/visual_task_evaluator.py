from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from world_model.index import WorldModelIndex


RELATION_ALIASES = {
    "near": {"near", "beside", "next_to", "adjacent_to"},
    "beside": {"near", "beside", "next_to", "adjacent_to"},
    "on": {"on", "atop"},
    "inside": {"inside", "in"},
    "under": {"under", "below"},
}
OBJECT_ALIASES = {
    "book": ["book", "books", "notebook", "booklet", "magazine"],
    "laptop": ["laptop", "computer"],
    "chair": ["chair", "armchair", "white_chair"],
    "bed": ["bed"],
}
ACTIVE_STATUSES = {"active"}


def evaluate_visual_task(task: str, world_model: Dict[str, Any], confidence_threshold: float = 0.45) -> Dict[str, Any]:
    task_lower = task.lower().strip()
    index = WorldModelIndex.from_world_model(world_model)
    relation_query = _parse_relation_query(task_lower)
    near_query = _parse_find_near(task_lower)
    identify = _parse_identify_location(task_lower)
    find = _parse_find_object(task_lower)

    if relation_query:
        subject, relation, target = relation_query
        return _evaluate_relation(task, world_model, index, subject, relation, target, confidence_threshold)
    if near_query:
        subject, target = near_query
        return _evaluate_relation(task, world_model, index, subject, "near", target, confidence_threshold)
    if identify:
        return _evaluate_location(task, world_model, index, identify, confidence_threshold)
    if find:
        return _evaluate_find(task, world_model, index, find, confidence_threshold)
    return _result(
        task=task,
        status="failed",
        success=False,
        answer=f"Unsupported visual task form: {task}",
        confidence=0.0,
        supporting_evidence=[],
        contradicting_evidence=[],
        missing_evidence=[
            _missing_evidence("task_form", task, "The visual task evaluator could not classify this request.")
        ],
        queried_entities=[],
        queried_relations=[],
        reason="unsupported_visual_task",
    )


def _evaluate_find(
    task: str,
    index: WorldModelIndex,
    object_name: str,
    confidence_threshold: float,
) -> Dict[str, Any]:
    obj = _find_visual_object(index, object_name)
    if not obj:
        return _result(
            task=task,
            status="failed",
            success=False,
            answer=f"I do not see {object_name}.",
            confidence=0.0,
            supporting_evidence=[],
            contradicting_evidence=[],
            missing_evidence=[_missing_evidence("object", object_name, "Target object is absent from world_model.objects.")],
            queried_entities=[object_name],
            queried_relations=[],
            reason=f"{object_name} not found.",
        )

    confidence = _object_confidence(obj)
    supporting = [_object_evidence(obj)]
    if confidence >= confidence_threshold:
        return _result(
            task=task,
            status="complete",
            success=True,
            answer=f"Found {obj.get('name') or object_name} in the visual world model.",
            confidence=confidence,
            supporting_evidence=supporting,
            contradicting_evidence=[],
            missing_evidence=[],
            queried_entities=[object_name],
            queried_relations=[],
            reason=f"{object_name} found as {obj.get('name') or object_name}.",
        )

    return _result(
        task=task,
        status="uncertain",
        success=False,
        answer=f"{object_name} may be present, but confidence is below threshold.",
        confidence=confidence,
        supporting_evidence=supporting,
        contradicting_evidence=[],
        missing_evidence=[
            _missing_evidence(
                "object_confidence",
                object_name,
                f"Object confidence {confidence:.2f} is below threshold {confidence_threshold:.2f}.",
            )
        ],
        queried_entities=[object_name],
        queried_relations=[],
        reason=f"{object_name} exists but confidence is low.",
    )


def _evaluate_location(
    task: str,
    world_model: Dict[str, Any],
    index: WorldModelIndex,
    object_name: str,
    confidence_threshold: float,
) -> Dict[str, Any]:
    obj = _find_visual_object(index, object_name)
    if not obj:
        return _result(
            task=task,
            status="failed",
            success=False,
            answer=f"I cannot identify where {object_name} is.",
            confidence=0.0,
            supporting_evidence=[],
            contradicting_evidence=[],
            missing_evidence=[_missing_evidence("object", object_name, "Target object is absent from world_model.objects.")],
            queried_entities=[object_name],
            queried_relations=[],
            reason=f"{object_name} not found.",
        )

    object_actual_name = str(obj.get("name") or object_name)
    location = obj.get("location", {})
    if not isinstance(location, dict):
        location = {}
    support = str(location.get("support") or "")
    room = str(location.get("room") or "")
    status = str(location.get("status") or "")
    confidence = float(location.get("confidence", _object_confidence(obj)))
    supporting = [_object_evidence(obj)]
    active_relation = _best_location_relation(world_model, object_actual_name)
    if active_relation:
        supporting.append(_relation_evidence(active_relation, source="world_model.relations"))
    missing = []
    if not (support or room or active_relation):
        missing.append(_missing_evidence("location", object_name, "No room, support, or active location relation is known."))
    if status == "unknown":
        missing.append(_missing_evidence("location_status", object_name, "Object location.status is unknown."))
    if confidence < confidence_threshold:
        missing.append(
            _missing_evidence(
                "location_confidence",
                object_name,
                f"Location confidence {confidence:.2f} is below threshold {confidence_threshold:.2f}.",
            )
        )

    if supporting and not missing:
        answer = _location_answer(object_actual_name, room, support, active_relation)
        return _result(
            task=task,
            status="complete",
            success=True,
            answer=answer,
            confidence=confidence,
            supporting_evidence=supporting,
            contradicting_evidence=[],
            missing_evidence=[],
            queried_entities=[object_name],
            queried_relations=["location"],
            reason=answer,
        )

    return _result(
        task=task,
        status="uncertain",
        success=False,
        answer=f"I found {object_actual_name}, but its location is uncertain.",
        confidence=confidence,
        supporting_evidence=supporting,
        contradicting_evidence=[],
        missing_evidence=missing,
        queried_entities=[object_name],
        queried_relations=["location"],
        reason=f"{object_name} location is uncertain.",
    )


def _evaluate_relation(
    task: str,
    world_model: Dict[str, Any],
    index: WorldModelIndex,
    subject: str,
    relation: str,
    target: str,
    confidence_threshold: float,
) -> Dict[str, Any]:
    subject_obj = _find_visual_object(index, subject)
    target_obj = _find_visual_object(index, target)
    queried_relation = f"{subject} {relation} {target}"
    supporting: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    contradicting: List[Dict[str, Any]] = []

    if subject_obj:
        supporting.append(_object_evidence(subject_obj))
    else:
        missing.append(_missing_evidence("object", subject, "Subject object is absent from world_model.objects."))
    if target_obj:
        supporting.append(_object_evidence(target_obj))
    else:
        missing.append(_missing_evidence("object", target, "Target object is absent from world_model.objects."))
    if missing:
        return _result(
            task=task,
            status="failed",
            success=False,
            answer=f"I cannot answer because required entities are missing: {', '.join(_missing_labels(missing))}.",
            confidence=0.0,
            supporting_evidence=supporting,
            contradicting_evidence=[],
            missing_evidence=missing,
            queried_entities=[subject, target],
            queried_relations=[queried_relation],
            reason="missing_entities",
        )

    subject_name = str(subject_obj.get("name") or subject)
    target_name = str(target_obj.get("name") or target)
    matched = _find_relation(world_model, subject_name, relation, target_name, require_active=False)
    active_match = matched if matched and matched.get("status") in ACTIVE_STATUSES else None
    if active_match and float(active_match.get("confidence", 0.0)) >= confidence_threshold:
        relation_evidence = _relation_evidence(active_match, source="world_model.relations")
        return _result(
            task=task,
            status="complete",
            success=True,
            answer=f"Yes, {subject_name} is {active_match.get('relation')} {target_name}.",
            confidence=float(active_match.get("confidence", 0.0)),
            supporting_evidence=supporting + [relation_evidence],
            contradicting_evidence=[],
            missing_evidence=[],
            queried_entities=[subject, target],
            queried_relations=[queried_relation],
            reason="active_relation_found",
        )

    if matched:
        if matched.get("status") in {"stale", "uncertain"}:
            missing.append(
                _missing_evidence(
                    "active_relation",
                    queried_relation,
                    f"A matching relation exists but its status is {matched.get('status')}, not active.",
                    related_content=matched,
                )
            )
        else:
            missing.append(
                _missing_evidence(
                    "relation_confidence",
                    queried_relation,
                    f"Matching relation confidence {float(matched.get('confidence', 0.0)):.2f} is below threshold.",
                    related_content=matched,
                )
            )
    else:
        missing.append(
            _missing_evidence(
                "active_relation",
                queried_relation,
                "Both objects are present, but no explicit active relation supports the requested relation.",
            )
        )

    contradicting = _contradicting_relations(world_model, subject_name, relation, target_name)
    confidence = _aggregate_confidence(supporting, default=0.35)
    answer = f"I cannot confirm that {subject_name} is {relation} {target_name} from the current visual world model."
    return _result(
        task=task,
        status="uncertain",
        success=False,
        answer=answer,
        confidence=confidence,
        supporting_evidence=supporting,
        contradicting_evidence=contradicting,
        missing_evidence=missing,
        queried_entities=[subject, target],
        queried_relations=[queried_relation],
        reason="relation_not_confirmed",
    )


def _result(
    *,
    task: str,
    status: str,
    success: bool,
    answer: str,
    confidence: float,
    supporting_evidence: List[Dict[str, Any]],
    contradicting_evidence: List[Dict[str, Any]],
    missing_evidence: List[Dict[str, Any]],
    queried_entities: List[str],
    queried_relations: List[str],
    reason: str,
) -> Dict[str, Any]:
    confidence = max(0.0, min(1.0, float(confidence)))
    summary = _evidence_summary(status, confidence, supporting_evidence, contradicting_evidence, missing_evidence)
    all_evidence = supporting_evidence + contradicting_evidence + missing_evidence
    return {
        "task": task,
        "status": status,
        "success": success,
        "reason": reason,
        "answer": answer,
        "confidence": confidence,
        "supporting_evidence": supporting_evidence,
        "contradicting_evidence": contradicting_evidence,
        "missing_evidence": missing_evidence,
        "evidence_summary": summary,
        "queried_entities": queried_entities,
        "queried_relations": queried_relations,
        "evidence": [_legacy_evidence_text(item) for item in all_evidence],
    }


def _object_evidence(obj: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "object",
        "source": "world_model.objects",
        "content": obj,
        "frame_ids": _frame_ids(obj),
        "confidence": _object_confidence(obj),
    }


def _relation_evidence(relation: Dict[str, Any], source: str = "world_model.relations") -> Dict[str, Any]:
    return {
        "type": "relation",
        "source": source,
        "content": relation,
        "frame_ids": _frame_ids(relation),
        "confidence": float(relation.get("confidence", 0.0)),
    }


def _missing_evidence(
    missing_type: str,
    label: str,
    reason: str,
    related_content: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    content: Dict[str, Any] = {"missing_type": missing_type, "label": label, "reason": reason}
    if related_content:
        content["related_content"] = related_content
    return {
        "type": "uncertainty",
        "source": "visual_task_evaluator",
        "content": content,
        "frame_ids": _frame_ids(related_content or {}),
        "confidence": 0.0,
    }


def _frame_ids(item: Dict[str, Any]) -> List[int]:
    frame_values: List[int] = []
    for key in ("frame_id", "frame_index", "observed_at_step", "last_observed_step"):
        value = item.get(key)
        if isinstance(value, int):
            frame_values.append(value)
    if isinstance(item.get("frame_ids"), list):
        frame_values.extend(value for value in item["frame_ids"] if isinstance(value, int))
    return sorted(set(frame_values))


def _evidence_summary(
    status: str,
    confidence: float,
    supporting: List[Dict[str, Any]],
    contradicting: List[Dict[str, Any]],
    missing: List[Dict[str, Any]],
) -> str:
    support_text = f"{len(supporting)} supporting"
    contradiction_text = f"{len(contradicting)} contradicting"
    missing_text = f"{len(missing)} missing"
    if status == "complete":
        return f"Complete with confidence {confidence:.2f}: {support_text} evidence item(s), no required evidence missing."
    if status == "uncertain":
        return (
            f"Uncertain with confidence {confidence:.2f}: {support_text} evidence item(s), "
            f"{contradiction_text} evidence item(s), and {missing_text} evidence item(s)."
        )
    return f"Failed with confidence {confidence:.2f}: {missing_text} evidence item(s)."


def _legacy_evidence_text(evidence: Dict[str, Any]) -> str:
    content = evidence.get("content", {})
    if evidence.get("type") == "object" and isinstance(content, dict):
        return f"object={content.get('name') or content.get('id')} confidence={evidence.get('confidence', 0.0)}"
    if evidence.get("type") == "relation" and isinstance(content, dict):
        return (
            f"relation={content.get('subject')} {content.get('relation')} {content.get('object')} "
            f"status={content.get('status')} confidence={evidence.get('confidence', 0.0)}"
        )
    if evidence.get("type") == "uncertainty" and isinstance(content, dict):
        return f"missing={content.get('label')} reason={content.get('reason')}"
    return str(content)


def _missing_labels(missing: Iterable[Dict[str, Any]]) -> List[str]:
    labels = []
    for item in missing:
        content = item.get("content", {})
        if isinstance(content, dict):
            labels.append(str(content.get("label", "unknown")))
    return labels


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


def _find_visual_object(index: WorldModelIndex, object_name: str) -> Dict[str, Any] | None:
    candidates = OBJECT_ALIASES.get(object_name, [object_name])
    normalized_candidates = {_normalize_object(candidate) for candidate in candidates}
    for candidate in candidates:
        exact = index.find_object(candidate)
        if exact:
            return exact
    for obj in index.iter_objects():
        values = {_normalize_object(str(obj.get("name") or "")), _normalize_object(str(obj.get("id") or ""))}
        if values & normalized_candidates:
            return obj
        if any(_matches_alias(value, normalized_candidates) for value in values):
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
        if not _matches_alias(_normalize_object(str(relation.get("subject", ""))), {_normalize_object(subject)}):
            continue
        if relation.get("status") in ACTIVE_STATUSES:
            return relation
    return None


def _find_relation(
    world_model: Dict[str, Any],
    subject: str,
    relation_name: str,
    target: str,
    require_active: bool = True,
) -> Dict[str, Any] | None:
    accepted_relations = RELATION_ALIASES.get(relation_name, {relation_name})
    target_aliases = {_normalize_object(value) for value in OBJECT_ALIASES.get(_normalize_object(target), [target])}
    subject_aliases = {_normalize_object(value) for value in OBJECT_ALIASES.get(_normalize_object(subject), [subject])}
    best_non_active = None
    for relation in world_model.get("relations", []):
        if not isinstance(relation, dict):
            continue
        rel_subject = _normalize_object(str(relation.get("subject", "")))
        rel_object = _normalize_object(str(relation.get("object", "")))
        if not _matches_alias(rel_subject, subject_aliases) or not _matches_alias(rel_object, target_aliases):
            continue
        if relation.get("relation") not in accepted_relations:
            continue
        if relation.get("status") in ACTIVE_STATUSES:
            return relation
        best_non_active = best_non_active or relation
    return None if require_active else best_non_active


def _contradicting_relations(
    world_model: Dict[str, Any],
    subject: str,
    relation_name: str,
    target: str,
) -> List[Dict[str, Any]]:
    accepted_relations = RELATION_ALIASES.get(relation_name, {relation_name})
    subject_aliases = {_normalize_object(value) for value in OBJECT_ALIASES.get(_normalize_object(subject), [subject])}
    target_aliases = {_normalize_object(value) for value in OBJECT_ALIASES.get(_normalize_object(target), [target])}
    contradictions: List[Dict[str, Any]] = []
    for relation in world_model.get("relations", []):
        if not isinstance(relation, dict):
            continue
        if relation.get("status") not in ACTIVE_STATUSES:
            continue
        if relation.get("relation") not in accepted_relations:
            continue
        rel_subject = _normalize_object(str(relation.get("subject", "")))
        rel_object = _normalize_object(str(relation.get("object", "")))
        if not _matches_alias(rel_subject, subject_aliases):
            continue
        if _matches_alias(rel_object, target_aliases):
            continue
        contradictions.append(_relation_evidence(relation, source="world_model.relations"))
    return contradictions


def _aggregate_confidence(evidence: List[Dict[str, Any]], default: float = 0.0) -> float:
    values = [float(item.get("confidence", 0.0)) for item in evidence if item.get("confidence") is not None]
    if not values:
        return default
    return sum(values) / len(values)


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
