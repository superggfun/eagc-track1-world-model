import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set


def validate(world_model_path: Path, audit_path: Path) -> List[str]:
    errors: List[str] = []
    world_model = _read_json(world_model_path, errors, "world_model")
    audit = _read_json(audit_path, errors, "run_audit")
    if errors:
        return errors

    objects = world_model.get("objects", [])
    if not isinstance(objects, list) or not objects:
        errors.append("vision world_model.objects must be non-empty.")
        objects = []
    if len([obj for obj in objects if isinstance(obj, dict)]) < 2:
        errors.append("vision world_model.objects must include at least 2 objects.")

    object_names = _object_names(objects)
    relations = world_model.get("relations", [])
    if isinstance(relations, list):
        for index, relation in enumerate(relations):
            if not isinstance(relation, dict):
                errors.append(f"relations[{index}] must be an object.")
                continue
            for endpoint in ["subject", "object"]:
                value = relation.get(endpoint)
                if value and value not in object_names:
                    errors.append(f"relations[{index}].{endpoint}={value!r} is not present in objects.")
    else:
        errors.append("relations must be a list.")

    if audit.get("vision_mode") is True:
        if not audit.get("image_path"):
            errors.append("vision run_audit must include image_path.")
        if audit.get("vision_call_success") is not True:
            errors.append("vision run_audit must record vision_call_success=true.")
    else:
        errors.append("run_audit.vision_mode must be true for vision validation.")

    return errors


def _read_json(path: Path, errors: List[str], label: str) -> Dict[str, Any]:
    if not path.exists():
        errors.append(f"Missing {label} file: {path}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid {label} JSON: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{label} must be a JSON object.")
        return {}
    return data


def _object_names(objects: Any) -> Set[str]:
    names: Set[str] = set()
    if not isinstance(objects, list):
        return names
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        if obj.get("id"):
            names.add(str(obj["id"]))
        if obj.get("name"):
            names.add(str(obj["name"]))
    return names


def main() -> int:
    world_model_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/world_model.json")
    audit_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("outputs/run_audit.json")
    errors = validate(world_model_path, audit_path)
    if errors:
        print("Vision extraction validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Vision extraction validation passed: {world_model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
