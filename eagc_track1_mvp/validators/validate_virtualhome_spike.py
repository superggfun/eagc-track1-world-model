from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set


GRACEFUL_FAILURE_REASONS = {
    "missing_virtualhome_executable",
    "missing_virtualhome_simulator_path",
    "virtualhome_python_api_not_installed",
    "virtualhome_environment_not_ready",
}


def validate(status_path: Path) -> List[str]:
    errors: List[str] = []
    status = _read_json(status_path, errors, "status")
    if errors:
        return errors

    output_dir = status_path.parent
    if status.get("success") is not True:
        reason = status.get("reason")
        if reason not in GRACEFUL_FAILURE_REASONS:
            errors.append(f"VirtualHome failure reason is not graceful or recognized: {reason!r}")
        if not status.get("download_hint") and reason in {
            "missing_virtualhome_executable",
            "missing_virtualhome_simulator_path",
            "virtualhome_python_api_not_installed",
        }:
            errors.append("Graceful VirtualHome failure should include download_hint.")
        return errors

    required = [
        output_dir / "scene_graph.json",
        output_dir / "converted_world_model.json",
        output_dir / "converted_episode_log.jsonl",
    ]
    for path in required:
        if not path.exists() or path.stat().st_size == 0:
            errors.append(f"Required VirtualHome artifact missing or empty: {path}")

    if errors:
        return errors

    world_model = _read_json(output_dir / "converted_world_model.json", errors, "converted_world_model")
    if errors:
        return errors
    objects = world_model.get("objects", [])
    if not isinstance(objects, list) or not objects:
        errors.append("converted_world_model.objects must be non-empty for a successful VirtualHome spike.")
    object_names = _object_names(objects)
    relations = world_model.get("relations", [])
    if not isinstance(relations, list):
        errors.append("converted_world_model.relations must be a list.")
    else:
        for index, relation in enumerate(relations):
            if not isinstance(relation, dict):
                errors.append(f"relations[{index}] must be an object.")
                continue
            subject = relation.get("subject")
            obj = relation.get("object")
            if subject and subject not in object_names:
                errors.append(f"relations[{index}].subject={subject!r} missing from objects.")
            if obj and obj not in object_names and obj not in _room_names(world_model):
                errors.append(f"relations[{index}].object={obj!r} missing from objects/rooms.")
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
        if isinstance(obj, dict):
            if obj.get("name"):
                names.add(str(obj["name"]))
            if obj.get("id"):
                names.add(str(obj["id"]))
    return names


def _room_names(world_model: Dict[str, Any]) -> Set[str]:
    names: Set[str] = set()
    rooms = world_model.get("rooms", [])
    if isinstance(rooms, list):
        for room in rooms:
            if isinstance(room, dict):
                names.add(str(room.get("name") or room.get("id") or ""))
    return names


def main() -> int:
    status_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/virtualhome_spike/status.json")
    errors = validate(status_path)
    if errors:
        print("VirtualHome spike validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"VirtualHome spike validation passed: {status_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
