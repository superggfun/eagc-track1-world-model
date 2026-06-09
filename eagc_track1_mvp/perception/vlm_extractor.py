import json
import re
from pathlib import Path
from typing import Any, Dict, List

from clients.qwen_client import QwenClient, QwenClientError
from perception.json_utils import parse_json_from_text
from perception.prompts import (
    EXTRACTOR_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_extraction_prompt,
    build_vision_extraction_prompt,
)


REQUIRED_EXTRACTION_KEYS = [
    "rooms",
    "topology",
    "objects",
    "relations",
    "states",
    "affordances",
    "uncertainty",
]


class VLMExtractor:
    """Text-only extractor. Image inputs can be added behind this interface later."""

    def __init__(
        self,
        client: QwenClient,
        debug_output_path: Path | None = None,
        response_summary_path: Path | None = None,
    ) -> None:
        self.client = client
        self.debug_output_path = debug_output_path
        self.response_summary_path = response_summary_path
        self.fallback_used = False
        self.last_parse_summary: Dict[str, Any] = {}
        self.last_input_mode = "text"
        self.last_parse_success = False
        self.last_call_success = False

    def extract(self, observation: str | Dict[str, Any], task: str) -> Dict[str, Any]:
        self.fallback_used = False
        self.last_parse_success = False
        self.last_call_success = False
        raw_text, observation_text, input_mode = self._call_model(observation, task)
        self.last_call_success = True
        raw_update: Dict[str, Any]
        parsed_ok = False
        parse_error = ""
        try:
            raw_update = parse_json_from_text(raw_text)
            parsed_ok = True
        except (ValueError, TypeError) as exc:
            parse_error = str(exc)
            self.fallback_used = True
            self._save_raw_output(raw_text)
            raw_update = fallback_minimal_extraction(observation_text, note=parse_error)
        self.last_parse_success = parsed_ok
        self._save_response_summary(raw_text, raw_update, parsed_ok, parse_error, input_mode)
        return normalize_extraction(raw_update)

    def _call_model(self, observation: str | Dict[str, Any], task: str) -> tuple[str, str, str]:
        if isinstance(observation, dict) and observation.get("image_path"):
            self.last_input_mode = "vision"
            observation_text = str(observation.get("text", ""))
            prompt = build_vision_extraction_prompt(observation_text, task)
            if not hasattr(self.client, "chat_vision"):
                raise QwenClientError("Configured client does not support vision chat completions.")
            return self.client.chat_vision(str(observation["image_path"]), prompt), observation_text, "vision"

        self.last_input_mode = "text"
        observation_text = str(observation)
        messages = [
            {"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT},
            {"role": "user", "content": build_extraction_prompt(observation_text, task)},
        ]
        chat_text = getattr(self.client, "chat_text", self.client.chat)
        return chat_text(messages), observation_text, "text"

    def _save_raw_output(self, raw_text: str) -> None:
        if self.debug_output_path is None:
            return
        self.debug_output_path.parent.mkdir(parents=True, exist_ok=True)
        self.debug_output_path.write_text(raw_text, encoding="utf-8")

    def _save_response_summary(
        self,
        raw_text: str,
        raw_update: Dict[str, Any],
        parsed_ok: bool,
        parse_error: str,
        input_mode: str,
    ) -> None:
        top_level_keys = sorted(raw_update.keys()) if isinstance(raw_update, dict) else []
        summary = {
            "prompt_version": PROMPT_VERSION,
            "input_mode": input_mode,
            "raw_chars": len(raw_text),
            "parsed_ok": parsed_ok,
            "fallback_used": self.fallback_used,
            "top_level_keys": top_level_keys,
            "missing_keys": [key for key in REQUIRED_EXTRACTION_KEYS if key not in top_level_keys],
            "parse_error": parse_error,
        }
        self.last_parse_summary = summary
        if self.response_summary_path is None or getattr(self.client, "base_url", "") == "mock://local":
            return
        self.response_summary_path.parent.mkdir(parents=True, exist_ok=True)
        self.response_summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def normalize_extraction(update: Dict[str, Any]) -> Dict[str, Any]:
    defaults = {
        "rooms": [],
        "topology": [],
        "objects": [],
        "relations": [],
        "states": [],
        "affordances": [],
        "uncertainty": [],
    }
    normalized = {**defaults, **{k: v for k, v in update.items() if k in defaults}}
    for key in defaults:
        if not isinstance(normalized[key], list):
            normalized[key] = []
    normalized["relations"] = normalize_relations(normalized["relations"])
    normalized["objects"] = normalize_objects(
        normalized["objects"], normalized["states"], normalized["relations"]
    )
    normalized["affordances"] = normalize_affordances(normalized["affordances"])
    return normalized


def normalize_objects(
    objects: List[Any], states: List[Any], relations: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    object_names = set()
    for item in objects:
        if isinstance(item, str):
            obj: Dict[str, Any] = {"name": item}
        elif isinstance(item, dict):
            obj = dict(item)
        else:
            continue

        name = str(obj.get("name") or obj.get("id") or "unknown_object").strip()
        object_id = str(obj.get("id") or _slug(name))
        category = obj.get("category") or obj.get("type") or "object"
        location = normalize_location(
            obj.get("location") or _state_value(states, name, "location"),
            room=str(obj.get("room") or "unknown"),
            support=_support_for_subject(relations, name),
            confidence=float(obj.get("confidence", 0.75)),
        )
        state = obj.get("state") or _state_value(states, name, "state") or "observed"

        obj.update(
            {
                "id": object_id,
                "name": name,
                "category": category,
                "location": location,
                "state": state,
            }
        )
        obj.pop("type", None)
        normalized.append(obj)
        object_names.add(name)
        object_names.add(object_id)

    for support in _missing_relation_objects(relations, object_names):
        normalized.append(
            {
                "id": _slug(support),
                "name": support,
                "category": "inferred_support",
                "location": normalize_location(None, room=_first_room(normalized), status="inferred", confidence=0.55),
                "state": "inferred",
            }
        )
    return normalized


def normalize_relations(relations: List[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        normalized.append(
            {
                "subject": str(relation.get("subject", "")),
                "relation": str(relation.get("relation", "")),
                "object": str(relation.get("object", "")),
                "status": relation.get("status", "active"),
                "confidence": float(relation.get("confidence", 0.75)),
                "observed_at_step": int(relation.get("observed_at_step", 1)),
            }
        )
    return normalized


def normalize_location(
    raw_location: Any,
    room: str,
    support: str = "",
    status: str = "known",
    confidence: float = 0.75,
) -> Dict[str, Any]:
    if isinstance(raw_location, dict):
        return {
            "room": str(raw_location.get("room", room or "")),
            "region": str(raw_location.get("region", "visible_area")),
            "support": str(raw_location.get("support", support or "")),
            "status": str(raw_location.get("status", status)),
            "confidence": float(raw_location.get("confidence", confidence)),
        }
    if isinstance(raw_location, str) and raw_location == "unknown":
        return {"room": room or "", "region": "", "support": "", "status": "unknown", "confidence": 0.0}
    return {
        "room": room or "",
        "region": "visible_area",
        "support": support or "",
        "status": status,
        "confidence": confidence,
    }


def normalize_affordances(affordances: List[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for affordance in affordances:
        if not isinstance(affordance, dict):
            continue
        obj = str(affordance.get("object", "object"))
        actions = [_normalize_affordance_action(obj, action) for action in affordance.get("actions", [])]
        normalized.append({"object": obj, "actions": [action for action in actions if action]})
    return normalized


def fallback_minimal_extraction(observation: str, note: str = "") -> Dict[str, Any]:
    room_match = re.search(r"Room:\s*([A-Za-z0-9_-]+)", observation)
    room = room_match.group(1) if room_match else "unknown"
    visible_match = re.search(r"Visible objects:\s*([^.]*)", observation)
    names = []
    if visible_match:
        names = [name.strip() for name in visible_match.group(1).split(",") if name.strip()]

    objects = [
        {
            "id": _slug(name),
            "name": name,
            "category": "object",
            "location": normalize_location(None, room=room, confidence=0.5),
            "state": "observed",
        }
        for name in names
    ]
    return {
        "rooms": [room] if room != "unknown" else [],
        "topology": [],
        "objects": objects,
        "relations": [],
        "states": [],
        "affordances": [],
        "uncertainty": [
            {
                "item": "perception_json_parse",
                "reason": f"Used fallback extraction. {note}".strip(),
                "level": "high",
            }
        ],
    }


def _state_value(states: List[Any], entity: str, attribute: str) -> str | None:
    for state in states:
        if not isinstance(state, dict):
            continue
        if state.get("entity") == entity and state.get("attribute") == attribute:
            value = state.get("value")
            return str(value) if value is not None else None
    return None


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "unknown_object"


def _support_for_subject(relations: List[Dict[str, Any]], subject: str) -> str:
    for relation in relations:
        if relation.get("subject") == subject and relation.get("relation") in {"on", "inside", "near"}:
            return str(relation.get("object", ""))
    return ""


def _missing_relation_objects(relations: List[Dict[str, Any]], object_names: set[str]) -> List[str]:
    missing = []
    for relation in relations:
        target = relation.get("object", "")
        if not target or target in object_names or _slug(target) in object_names:
            continue
        if target not in missing:
            missing.append(target)
    return missing


def _first_room(objects: List[Dict[str, Any]]) -> str:
    for obj in objects:
        location = obj.get("location", {})
        if isinstance(location, dict) and location.get("room"):
            return str(location["room"])
    return "unknown"


def _normalize_affordance_action(obj: str, action: Any) -> str:
    text = str(action).strip().lower().replace(" ", "_")
    if text.startswith("pick"):
        return f"pick_up({_slug(obj)})"
    if text.startswith("open"):
        return f"open({_slug(obj)})"
    if text.startswith("close"):
        return f"close({_slug(obj)})"
    if text.startswith("place"):
        return ""
    if text.startswith("search"):
        return f"search({_slug(obj)})"
    if text.startswith("locate"):
        return f"locate({_slug(obj)})"
    return ""
