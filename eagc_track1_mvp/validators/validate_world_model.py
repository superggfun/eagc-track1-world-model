import json
import sys
from pathlib import Path
from typing import Any, Dict, List


REQUIRED_FIELDS = [
    "episode_id",
    "agent_state",
    "rooms",
    "topology",
    "objects",
    "relations",
    "states",
    "affordances",
    "uncertainty",
    "plans",
    "exceptions",
    "task_status",
]


def validate(path: Path) -> List[str]:
    errors: List[str] = []
    if not path.exists():
        return [f"Missing world model file: {path}"]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON: {exc}"]

    if not isinstance(data, dict):
        return ["World model must be a JSON object."]

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    objects = data.get("objects", [])
    if not isinstance(objects, list):
        errors.append("objects must be a list.")
    else:
        errors.extend(_validate_objects(objects))

    plans = data.get("plans", [])
    if not isinstance(plans, list) or not plans:
        errors.append("plans must be a non-empty list.")
    else:
        for index, plan in enumerate(plans):
            if not isinstance(plan, dict):
                errors.append(f"plans[{index}] must be an object.")
                continue
            if not plan.get("subgoals"):
                errors.append(f"plans[{index}] is missing subgoals.")
            if not plan.get("actions"):
                errors.append(f"plans[{index}] is missing actions.")

    exceptions = data.get("exceptions", [])
    if not isinstance(exceptions, list):
        errors.append("exceptions must be a list.")
    elif exceptions:
        if not any(_has_exception_and_recovery(item) for item in exceptions):
            errors.append("exceptions must include an exception event with a recovery_plan.")

    return errors


def _validate_objects(objects: List[Any]) -> List[str]:
    errors: List[str] = []
    seen_ids = set()
    for index, obj in enumerate(objects):
        if not isinstance(obj, dict):
            errors.append(f"objects[{index}] must be an object.")
            continue
        for field in ["id", "name", "category", "location", "state"]:
            if field not in obj or obj[field] in ("", None):
                errors.append(f"objects[{index}] is missing recommended field: {field}")
        location = obj.get("location")
        if not isinstance(location, dict):
            errors.append(f"objects[{index}].location must be a structured object.")
        else:
            for field in ["room", "region", "support", "status", "confidence"]:
                if field not in location:
                    errors.append(f"objects[{index}].location missing field: {field}")
        object_id = obj.get("id")
        if object_id in seen_ids:
            errors.append(f"Duplicate object id: {object_id}")
        if object_id is not None:
            seen_ids.add(object_id)
    return errors


def _has_exception_and_recovery(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    recovery_plan = item.get("recovery_plan")
    return bool(item.get("exception") and isinstance(recovery_plan, dict) and recovery_plan.get("actions"))


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/world_model.json")
    errors = validate(path)
    if errors:
        print("World model validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"World model validation passed: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
