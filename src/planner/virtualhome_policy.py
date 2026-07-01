from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ActionIntent:
    name: str
    target_label: Optional[str] = None
    reason: str = ""
    confidence: float = 0.0
    source: str = "agent_policy"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyContext:
    step: int
    task: str
    observation_text: str
    frame_path: Optional[str]
    world_model: Dict[str, Any]
    recent_events: List[Dict[str, Any]]
    available_actions: List[str]
    last_action: Optional[str] = None
    last_result: Optional[Dict[str, Any]] = None


# Backward-compatible name for older tests/imports. The policy now emits intents,
# not executable VirtualHome script actions.
ActionDecision = ActionIntent


class VirtualHomeExplorationPolicy:
    """Observation-driven intent policy for VirtualHome continuous evidence."""

    def decide(self, context: PolicyContext) -> ActionIntent:
        failed_targets = _recent_failed_targets(context.recent_events)
        observation = _parse_observation_text(context.observation_text)

        frontier = _first_unfailed(_frontier_labels(observation), failed_targets)
        if frontier:
            return ActionIntent(
                name="inspect_frontier",
                target_label=frontier,
                reason="Selected visible doorway/frontier cue from current observation for grounding.",
                confidence=0.72,
                metadata={"rank": "frontier", "step": context.step},
            )

        anchor = _first_unfailed(_visible_anchor_labels(observation), failed_targets)
        if anchor:
            return ActionIntent(
                name="approach_visible_anchor",
                target_label=anchor,
                reason="Selected visible object anchor as an observation-side navigation intent.",
                confidence=0.58,
                metadata={"rank": "visible_anchor", "step": context.step},
            )

        return _scan_intent(context, source="agent_policy", reason="No groundable semantic target was available; scanning for more evidence.")

    def fallback_intents(self, context: PolicyContext, attempted_intents: List[ActionIntent]) -> List[ActionIntent]:
        attempted_names = {intent.name for intent in attempted_intents}
        intents: List[ActionIntent] = []
        for name in ["scan_right", "scan_left", "observe", "stop"]:
            if name in attempted_names and name != "stop":
                continue
            intents.append(
                ActionIntent(
                    name=name,
                    reason="Bounded harness fallback after an intent could not be grounded or executed.",
                    confidence=0.25,
                    source="harness_fallback",
                    metadata={"fallback": True},
                )
            )
        return intents

    # Compatibility shim for older harness code paths.
    def fallback_decisions(self, context: PolicyContext, attempted_actions: List[str]) -> List[ActionIntent]:
        return self.fallback_intents(context, [])


def action_intent_to_dict(intent: ActionIntent) -> Dict[str, Any]:
    return {
        "name": intent.name,
        "action": intent.name,
        "target_label": intent.target_label,
        "reason": intent.reason,
        "confidence": intent.confidence,
        "source": intent.source,
        "metadata": dict(intent.metadata),
    }


def action_decision_to_dict(intent: ActionIntent) -> Dict[str, Any]:
    payload = action_intent_to_dict(intent)
    # Old consumers look for "action"; keep it as an intent name, not a script.
    payload["action"] = intent.name
    return payload


def _parse_observation_text(value: str) -> Dict[str, Any]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {"text": value}
    return payload if isinstance(payload, dict) else {"text": value}


def _frontier_labels(observation: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    for item in observation.get("topology_cues", []) if isinstance(observation.get("topology_cues"), list) else []:
        text = _clean_label(item)
        if text and _looks_like_frontier(text):
            labels.append(text)
    return _dedupe(labels)


def _visible_anchor_labels(observation: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    for item in observation.get("visible_objects", []) if isinstance(observation.get("visible_objects"), list) else []:
        text = _clean_label(item)
        if text and not _looks_like_surface(text):
            labels.append(text)
    return _dedupe(labels)


def _scan_intent(context: PolicyContext, *, source: str, reason: str) -> ActionIntent:
    last = str(context.last_action or "").lower()
    name = "scan_left" if "turnright" in last or "scan_right" in last else "scan_right"
    return ActionIntent(name=name, reason=reason, confidence=0.38, source=source, metadata={"rank": "scan"})


def _first_unfailed(values: List[str], failed_targets: set[str]) -> Optional[str]:
    for value in values:
        if value not in failed_targets:
            return value
    return None


def _recent_failed_targets(events: List[Dict[str, Any]]) -> set[str]:
    failed: set[str] = set()
    for event in events[-16:]:
        if not isinstance(event, dict):
            continue
        for key in ["target_label", "failed_target_label"]:
            value = _clean_label(event.get(key))
            if value:
                failed.add(value)
        for nested in event.get("fallback_events", []) if isinstance(event.get("fallback_events"), list) else []:
            if isinstance(nested, dict):
                value = _clean_label(nested.get("target_label") or nested.get("failed_target_label"))
                if value:
                    failed.add(value)
    return failed


def _looks_like_frontier(label: str) -> bool:
    return any(token in label for token in ["door", "doorway", "frontier", "passage", "exit", "entrance", "hallway"])


def _looks_like_surface(label: str) -> bool:
    return any(token in label for token in ["wall", "floor", "ceiling", "tile", "tiled", "window", "light", "lamp"])


def _clean_label(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        text = _clean_label(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
