from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def validate(world_model_path: Path, episode_log_path: Path) -> List[str]:
    errors: List[str] = []
    world_model = _read_json(world_model_path, errors, "converted_world_model")
    if errors:
        return errors

    if not world_model.get("episode_id"):
        errors.append("converted_world_model.episode_id must be non-empty.")
    if world_model.get("source") != "virtualhome":
        errors.append("converted_world_model.source must be 'virtualhome'.")
    if not isinstance(world_model.get("plans", []), list):
        errors.append("converted_world_model.plans must be a list.")

    objects = world_model.get("objects", [])
    if not isinstance(objects, list) or not objects:
        errors.append("converted_world_model.objects must be a non-empty list.")

    rooms = world_model.get("rooms", [])
    uncertainty = world_model.get("uncertainty", [])
    if not isinstance(rooms, list) or not rooms:
        if not uncertainty:
            errors.append("converted_world_model.rooms is empty and uncertainty does not explain missing rooms.")

    relations = world_model.get("relations", [])
    if not isinstance(relations, list):
        errors.append("converted_world_model.relations must be a list.")
    elif len(relations) < 5:
        errors.append("converted_world_model.relations should contain at least 5 scene graph relations.")

    log_errors = _validate_episode_log(episode_log_path)
    errors.extend(log_errors)

    program_log_path = world_model_path.parent / "program_log.json"
    if program_log_path.exists():
        program_log = _read_json(program_log_path, errors, "program_log")
        if isinstance(program_log, dict):
            tasks = program_log.get("tasks", [])
            program = program_log.get("program", [])
            if not isinstance(tasks, list) or not tasks:
                errors.append("program_log.tasks must be non-empty.")
            if not isinstance(program, list) or not program:
                errors.append("program_log.program must contain executed actions.")
            if tasks and not any(isinstance(task, dict) and task.get("status") == "success" for task in tasks):
                errors.append("program_log.tasks must contain at least one successful task.")

    return errors


def _validate_episode_log(path: Path) -> List[str]:
    errors: List[str] = []
    if not path.exists() or path.stat().st_size == 0:
        return [f"converted episode log missing or empty: {path}"]
    has_action = False
    has_result = False
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"episode_log line {line_number} is invalid JSON: {exc}")
            continue
        if not isinstance(row, dict):
            errors.append(f"episode_log line {line_number} must be a JSON object.")
            continue
        has_action = has_action or bool(row.get("action"))
        has_result = has_result or ("result" in row)
    if not has_action:
        errors.append("converted episode log must contain at least one action.")
    if not has_result:
        errors.append("converted episode log must contain result fields.")
    return errors


def _read_json(path: Path, errors: List[str], label: str) -> Dict[str, Any]:
    if not path.exists():
        errors.append(f"Missing {label}: {path}")
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


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "Usage: python -m validators.validate_virtualhome_converted_world_model "
            "outputs/virtualhome_spike/converted_world_model.json "
            "outputs/virtualhome_spike/converted_episode_log.jsonl"
        )
        return 2
    errors = validate(Path(sys.argv[1]), Path(sys.argv[2]))
    if errors:
        print("VirtualHome converted world model validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("VirtualHome converted world model validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

