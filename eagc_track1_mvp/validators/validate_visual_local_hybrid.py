from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


PHYSICAL_ACTION_PREFIXES = ("pick_up(", "place_on(", "place_in(", "open(", "close(", "unlock(", "use_tool(")


def validate(world_model_path: Path, audit_path: Path, episode_log_path: Path) -> List[str]:
    errors: List[str] = []
    world_model = _read_json(world_model_path, errors, "world_model")
    audit = _read_json(audit_path, errors, "run_audit")
    rows = _read_jsonl(episode_log_path, errors)
    if errors:
        return errors

    if audit.get("env") != "visual_sequence":
        errors.append(f"run_audit.env must be visual_sequence, got {audit.get('env')!r}.")
    if audit.get("visual_local_hybrid") is not True:
        errors.append("run_audit.visual_local_hybrid must be true.")
    if len(audit.get("processed_frames", [])) < 2:
        errors.append("visual-local hybrid requires at least 2 processed frames.")
    if not audit.get("visual_task"):
        errors.append("run_audit.visual_task is required.")
    if int(audit.get("symbolic_action_count", 0)) <= 0:
        errors.append("run_audit.symbolic_action_count must be positive.")

    event_types = [row.get("event_type") for row in rows]
    if "visual_world_model_built" not in event_types:
        errors.append("episode_log missing visual_world_model_built event.")
    if "task_received" not in event_types:
        errors.append("episode_log missing task_received event.")
    if "visual_world_model_built" in event_types and "task_received" in event_types:
        if event_types.index("task_received") < event_types.index("visual_world_model_built"):
            errors.append("task_received must occur after visual_world_model_built.")

    if not world_model.get("objects"):
        errors.append("world_model.objects must be non-empty.")
    if not world_model.get("plans"):
        errors.append("world_model.plans must be non-empty.")
    task_status = world_model.get("task_status")
    if not isinstance(task_status, dict):
        errors.append("world_model.task_status must exist.")
    else:
        for field in [
            "status",
            "success",
            "answer",
            "confidence",
            "supporting_evidence",
            "contradicting_evidence",
            "missing_evidence",
            "evidence_summary",
            "queried_entities",
            "queried_relations",
            "evidence",
        ]:
            if field not in task_status:
                errors.append(f"visual task_status missing field: {field}")
        if task_status.get("status") not in {"complete", "uncertain", "failed"}:
            errors.append(f"visual task_status has invalid status: {task_status.get('status')!r}")
        if task_status.get("status") == "complete" and not task_status.get("supporting_evidence"):
            errors.append("complete visual task_status requires supporting_evidence.")
        if task_status.get("status") == "uncertain" and not task_status.get("missing_evidence") and float(task_status.get("confidence", 0.0)) >= 0.6:
            errors.append("uncertain visual task_status requires missing_evidence or confidence < 0.6.")

    result_path_value = audit.get("visual_task_result_path")
    if not result_path_value:
        errors.append("run_audit.visual_task_result_path is required.")
    else:
        result_path = Path(str(result_path_value))
        if not result_path.exists():
            errors.append(f"visual_task_result_path does not exist: {result_path}")
        else:
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"visual_task_result_path is not valid JSON: {exc}")
            else:
                if isinstance(task_status, dict) and result.get("status") != task_status.get("status"):
                    errors.append("visual_task_result.status does not match world_model.task_status.status.")
                for field in ["supporting_evidence_count", "contradicting_evidence_count", "missing_evidence_count"]:
                    if field not in audit:
                        errors.append(f"run_audit missing field: {field}")

    task = str(audit.get("visual_task", "")).lower()
    if any(token in task for token in ["find", "identify", " is "]):
        if "symbolic_action" not in event_types and "answer" not in event_types:
            errors.append("visual query task requires symbolic_action or answer event.")

    for row in rows:
        action = str(row.get("action") or "")
        result = str(row.get("result") or "")
        if action.startswith(PHYSICAL_ACTION_PREFIXES) and result == "success":
            errors.append(f"physical action reported success in visual-local mode: {action}")
        if action.startswith(PHYSICAL_ACTION_PREFIXES) and result != "unsupported_in_visual_mode":
            errors.append(f"physical action must be unsupported in visual-local mode: {action}")

    unsupported_count = int(audit.get("unsupported_physical_action_count", 0))
    if unsupported_count < 0:
        errors.append("unsupported_physical_action_count cannot be negative.")
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
    if not path.exists():
        errors.append(f"Missing episode log: {path}")
        return []
    rows: List[Dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"episode_log line {line_number} invalid JSON: {exc}")
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def main() -> int:
    world_model_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/world_model.json")
    audit_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("outputs/run_audit.json")
    episode_log_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("outputs/episode_log.jsonl")
    errors = validate(world_model_path, audit_path, episode_log_path)
    if errors:
        print("Visual-local hybrid validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Visual-local hybrid validation passed: {world_model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
