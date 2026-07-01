from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from planner.virtualhome_policy import ActionIntent, action_intent_to_dict


ALLOWED_FINAL_TARGET_SOURCES = {
    "current_observation_runtime_metadata",
    "previously_verified_executable_target",
    "safe_scan_action",
}
DISALLOWED_FINAL_TARGET_SOURCES = {
    "environment_graph",
    "reference_world_model",
    "scene_graph_answer_key",
    "hardcoded_room_object_table",
    "mock_alias_map",
}


@dataclass
class GroundingContext:
    step: int
    observation_text: str
    frame_path: Optional[str]
    world_model: Dict[str, Any]
    observed_objects: List[Dict[str, Any]] = field(default_factory=list)
    recent_events: List[Dict[str, Any]] = field(default_factory=list)
    known_executable_targets: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    allowed_safe_scan_actions: Dict[str, str] = field(default_factory=dict)
    current_room: str = "unknown"
    frontiers: List[str] = field(default_factory=list)
    final_evidence: bool = True


@dataclass
class GroundedAction:
    intent: ActionIntent
    executable: bool
    vh_script: Optional[str] = None
    target_id: Optional[str] = None
    target_label: Optional[str] = None
    target_source: Optional[str] = None
    failure_reason: Optional[str] = None
    confidence: float = 0.0


class VirtualHomeActionGrounder:
    def ground(self, intent: ActionIntent, context: GroundingContext) -> GroundedAction:
        safe_scan = _safe_scan_script(intent.name, context.allowed_safe_scan_actions)
        if safe_scan:
            return GroundedAction(
                intent=intent,
                executable=True,
                vh_script=safe_scan,
                target_label=intent.name,
                target_source="safe_scan_action",
                confidence=max(intent.confidence, 0.95),
            )

        if intent.name == "observe":
            return GroundedAction(
                intent=intent,
                executable=True,
                vh_script=None,
                target_label="observe",
                target_source="safe_scan_action",
                confidence=max(intent.confidence, 0.8),
            )

        if intent.name == "stop":
            return GroundedAction(
                intent=intent,
                executable=False,
                target_label=intent.target_label,
                failure_reason="stop_requested",
                confidence=intent.confidence,
            )

        target_label = _normalize_label(intent.target_label)
        if not target_label:
            return _ungrounded(intent, "missing_target_label")

        target = _lookup_known_target(target_label, context)
        if not target:
            return _ungrounded(intent, "no_observation_side_executable_target")

        source = str(target.get("target_source") or "")
        if context.final_evidence and source not in ALLOWED_FINAL_TARGET_SOURCES:
            return _ungrounded(intent, f"disallowed_final_target_source:{source or 'unknown'}")
        if source in DISALLOWED_FINAL_TARGET_SOURCES:
            return _ungrounded(intent, f"disallowed_target_source:{source}")

        vh_script = str(target.get("vh_script") or "")
        target_id = str(target.get("target_id") or "")
        if not vh_script and target_id:
            verb = str(target.get("verb") or "Walk").strip("[]")
            label = _virtualhome_label(target.get("target_label") or target_label)
            vh_script = f"<char0> [{verb}] <{label}> ({target_id})"
        if not vh_script:
            return _ungrounded(intent, "known_target_missing_vh_script")

        return GroundedAction(
            intent=intent,
            executable=True,
            vh_script=vh_script,
            target_id=target_id or None,
            target_label=str(target.get("target_label") or target_label),
            target_source=source,
            confidence=max(intent.confidence, _safe_float(target.get("confidence"), 0.0)),
        )


def grounded_action_to_dict(action: GroundedAction) -> Dict[str, Any]:
    return {
        "intent": action_intent_to_dict(action.intent),
        "executable": action.executable,
        "vh_script": action.vh_script,
        "target_id": action.target_id,
        "target_label": action.target_label,
        "target_source": action.target_source,
        "failure_reason": action.failure_reason,
        "confidence": action.confidence,
    }


def _lookup_known_target(label: str, context: GroundingContext) -> Optional[Dict[str, Any]]:
    normalized = _normalize_label(label)
    for key in [normalized, label]:
        target = context.known_executable_targets.get(key)
        if isinstance(target, dict):
            return target
    for obj in context.observed_objects:
        if not isinstance(obj, dict):
            continue
        obj_label = _normalize_label(obj.get("name") or obj.get("label") or obj.get("id"))
        if obj_label != normalized:
            continue
        source = str(obj.get("target_source") or "")
        if source not in ALLOWED_FINAL_TARGET_SOURCES:
            continue
        if obj.get("vh_script") or obj.get("target_id"):
            return dict(obj)
    return None


def _ungrounded(intent: ActionIntent, reason: str) -> GroundedAction:
    return GroundedAction(
        intent=intent,
        executable=False,
        target_label=intent.target_label,
        failure_reason=reason,
        confidence=intent.confidence,
    )


def _safe_scan_script(name: str, configured: Dict[str, str]) -> Optional[str]:
    if name in configured:
        return configured[name]
    return {
        "scan_left": "<char0> [TurnLeft]",
        "turn_left": "<char0> [TurnLeft]",
        "scan_right": "<char0> [TurnRight]",
        "turn_right": "<char0> [TurnRight]",
        "look_around": "<char0> [LookAround]",
    }.get(name)


def _normalize_label(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _virtualhome_label(value: Any) -> str:
    return "".join(ch for ch in _normalize_label(value) if ch.isalnum() or ch == "_").strip("_")


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
