from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


GRACEFUL_FAILURE_REASONS = {"missing_alfred_dataset"}


def validate(status_path: Path) -> List[str]:
    errors: List[str] = []
    status = _read_json(status_path, errors, "status")
    if errors:
        return errors
    if status.get("success") is not True:
        reason = status.get("reason")
        if reason not in GRACEFUL_FAILURE_REASONS:
            errors.append(f"Unrecognized ALFRED conversion failure reason: {reason!r}")
        if reason == "missing_alfred_dataset" and not status.get("download_hint"):
            errors.append("missing_alfred_dataset should include download_hint.")
        return errors

    output_dir = status_path.parent
    world_model_path = output_dir / "world_model.json"
    episode_log_path = output_dir / "episode_log.jsonl"
    summary_path = output_dir / "alfred_task_summary.json"
    for path in [world_model_path, episode_log_path, summary_path]:
        if not path.exists() or path.stat().st_size == 0:
            errors.append(f"Required ALFRED artifact missing or empty: {path}")
    if errors:
        return errors

    world_model = _read_json(world_model_path, errors, "world_model")
    summary = _read_json(summary_path, errors, "alfred_task_summary")
    log_lines = _read_jsonl(episode_log_path, errors)
    if errors:
        return errors

    if world_model.get("source") != "alfred_offline":
        errors.append("world_model.source must be 'alfred_offline'.")
    if not str(world_model.get("task") or "").strip():
        errors.append("world_model.task/instruction must be non-empty.")
    if not str(summary.get("task") or "").strip():
        errors.append("alfred_task_summary.task must be non-empty.")
    event_types = {str(item.get("event_type")) for item in log_lines if isinstance(item, dict)}
    if not ({"action_loaded", "subgoal_loaded"} & event_types):
        errors.append("episode_log must contain at least one action_loaded or subgoal_loaded event.")
    uncertainty = world_model.get("uncertainty")
    if not isinstance(uncertainty, list) or not uncertainty:
        errors.append("world_model.uncertainty must explain offline visual-state limitations.")
    if not isinstance(world_model.get("objects", []), list):
        errors.append("world_model.objects must be a list, even if empty.")
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


def _read_jsonl(path: Path, errors: List[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid episode_log JSONL line {line_no}: {exc}")
            continue
        if not isinstance(item, dict):
            errors.append(f"episode_log line {line_no} must be an object.")
            continue
        items.append(item)
    if not items:
        errors.append("episode_log.jsonl must contain at least one event.")
    return items


def main() -> int:
    status_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/alfred_offline/status.json")
    errors = validate(status_path)
    if errors:
        print("ALFRED offline conversion validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"ALFRED offline conversion validation passed: {status_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
