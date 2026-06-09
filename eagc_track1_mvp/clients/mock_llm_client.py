import json
import re
from typing import Dict, List


class MockLLMClient:
    """Deterministic chat client for testing pipeline logic without vLLM."""

    def __init__(self, model: str = "deterministic-mock-llm", base_url: str = "mock://local") -> None:
        self.model = model
        self.base_url = base_url
        self.call_count = 0
        self.success_count = 0
        self.failure_count = 0

    def chat(self, messages: List[Dict[str, str]], *_args: object, **_kwargs: object) -> str:
        self.call_count += 1
        self.success_count += 1
        prompt = "\n".join(message.get("content", "") for message in messages)
        return json.dumps(_extract_for_prompt(prompt), ensure_ascii=False)


def _extract_for_prompt(prompt: str) -> Dict[str, object]:
    room = _match(prompt, r"Room:\s*([A-Za-z0-9_]+)") or "unknown"
    visible = _match(prompt, r"Visible objects:\s*([^.]*)") or ""
    names = [name.strip() for name in visible.split(",") if name.strip()]
    objects = [_object(name, room) for name in names]
    relations = []
    states = []
    affordances = []
    uncertainty = []

    text = prompt.lower()
    if "book is initially on the bed" in text:
        relations.extend(
            [
                _relation("book", "on", "bed"),
                _relation("book", "near", "pillow"),
                _relation("chair", "beside", "bed"),
                _relation("lamp", "on", "bedside_surface"),
            ]
        )
        objects.append(_object("bedside_surface", room, category="inferred_support"))
        states.append({"entity": "door", "attribute": "status", "value": "closed"})
        affordances.extend([{"object": "book", "actions": ["pick_up"]}, {"object": "door", "actions": ["open"]}])
    elif "hallway door is closed" in text:
        states.append({"entity": "door", "attribute": "status", "value": "closed"})
        affordances.append({"object": "door", "actions": ["open"]})
        uncertainty.append({"item": "door_lock_state", "reason": "Door may be locked.", "level": "medium"})
    elif "cup is on the counter" in text:
        relations.append(_relation("cup", "on", "counter"))
        states.append({"entity": "drawer", "attribute": "availability", "value": "limited"})
    elif "no screwdriver is visible" in text:
        objects.append(_object("screwdriver", room, category="tool", state="unavailable"))
        relations.extend([_relation("coin", "on", "desk"), _relation("lamp", "on", "desk")])
        uncertainty.append({"item": "screwdriver", "reason": "Required tool is absent.", "level": "high"})
    elif "remote is on the sofa" in text:
        relations.append(_relation("remote", "on", "sofa"))

    return {
        "rooms": [room] if room != "unknown" else [],
        "objects": _dedupe_objects(objects),
        "relations": relations,
        "states": states,
        "affordances": affordances,
        "uncertainty": uncertainty,
    }


def _object(name: str, room: str, category: str = "object", state: str = "observed") -> Dict[str, object]:
    return {"id": name, "name": name, "category": category, "room": room, "state": state}


def _relation(subject: str, relation: str, obj: str) -> Dict[str, object]:
    return {
        "subject": subject,
        "relation": relation,
        "object": obj,
        "status": "active",
        "confidence": 0.9,
        "observed_at_step": 1,
    }


def _dedupe_objects(objects: List[Dict[str, object]]) -> List[Dict[str, object]]:
    by_id: Dict[str, Dict[str, object]] = {}
    for obj in objects:
        by_id[str(obj["id"])] = obj
    return list(by_id.values())


def _match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1) if match else None
