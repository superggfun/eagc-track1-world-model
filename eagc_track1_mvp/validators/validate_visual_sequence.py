import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


LOCATION_RELATIONS = {"on", "inside", "under", "near", "beside", "at"}


def validate(world_model_path: Path, audit_path: Path, episode_log_path: Path) -> List[str]:
    errors: List[str] = []
    world_model = _read_json(world_model_path, errors, "world_model")
    audit = _read_json(audit_path, errors, "run_audit")
    rows = _read_jsonl(episode_log_path, errors)
    if errors:
        return errors

    processed_frames = audit.get("processed_frames", [])
    if not isinstance(processed_frames, list):
        errors.append("run_audit.processed_frames must be a list.")
        processed_frames = []
    if len(processed_frames) < 2:
        errors.append("visual_sequence must process at least 2 frames.")
    if audit.get("frame_count") != len(processed_frames):
        errors.append(
            f"run_audit.frame_count={audit.get('frame_count')} does not match processed frame count {len(processed_frames)}."
        )
    if audit.get("env") != "visual_sequence":
        errors.append(f"run_audit.env must be visual_sequence, got {audit.get('env')!r}.")
    frame_paths = audit.get("frame_paths", [])
    if not isinstance(frame_paths, list):
        errors.append("run_audit.frame_paths must be a list.")
        frame_paths = []
    elif frame_paths and frame_paths != processed_frames:
        errors.append("run_audit.frame_paths must match run_audit.processed_frames.")
    if not audit.get("use_mock_llm") and int(audit.get("qwen_call_count", 0)) < len(processed_frames):
        errors.append(
            f"run_audit.qwen_call_count={audit.get('qwen_call_count')} must be >= processed_frames={len(processed_frames)}."
        )
    if not audit.get("image_dir"):
        errors.append("run_audit.image_dir is required for visual_sequence.")

    perception_count = sum(1 for row in rows if row.get("event_type") == "perception")
    update_count = sum(1 for row in rows if row.get("event_type") == "world_model_update")
    if perception_count < 2 or update_count < 2:
        errors.append("episode_log must contain multiple perception and world_model_update events.")

    objects = world_model.get("objects", [])
    if not isinstance(objects, list) or not objects:
        errors.append("world_model.objects must be non-empty for visual_sequence.")
        objects = []

    object_ids: set[str] = set()
    object_names: set[str] = set()
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        object_id = str(obj.get("id") or "")
        object_name = str(obj.get("name") or object_id)
        if object_id:
            if object_id in object_ids:
                errors.append(f"Duplicate object id in world_model.objects: {object_id}")
            object_ids.add(object_id)
            object_ids.add(_slug(object_id))
        if object_name:
            object_names.add(object_name)
            object_names.add(_slug(object_name))

    active_by_subject: Dict[str, List[Dict[str, Any]]] = {}
    all_location_by_subject: Dict[str, List[Dict[str, Any]]] = {}
    for relation in world_model.get("relations", []):
        if (
            isinstance(relation, dict)
            and relation.get("relation") in LOCATION_RELATIONS
        ):
            subject = str(relation.get("subject"))
            all_location_by_subject.setdefault(subject, []).append(relation)
            if relation.get("status") == "active":
                active_by_subject.setdefault(subject, []).append(relation)
    for subject, relations in active_by_subject.items():
        if len(relations) > 1:
            rendered = [f"{rel.get('relation')} {rel.get('object')}" for rel in relations]
            errors.append(f"{subject} has multiple active location relations: {rendered}")
    for subject, relations in all_location_by_subject.items():
        unique_targets = {
            (relation.get("relation"), relation.get("object"))
            for relation in relations
            if relation.get("relation") in LOCATION_RELATIONS
        }
        if len(unique_targets) > 1 and not any(relation.get("status") == "stale" for relation in relations):
            errors.append(f"{subject} has changed location relations but no stale prior relation.")

    frame_observations = _frame_observations(rows)
    if len(frame_observations) >= 2:
        ever_observed: set[str] = set()
        for _, observed in frame_observations:
            ever_observed.update(observed)
        missing = sorted(name for name in ever_observed if _slug(name) not in object_names and _slug(name) not in object_ids)
        for name in missing:
            errors.append(f"Object observed in an earlier frame was deleted from world_model.objects: {name}")

        final_observed = frame_observations[-1][1]
        not_currently_visible = sorted(name for name in ever_observed - final_observed)
        visibility_states = {
            _slug(str(state.get("entity")))
            for state in world_model.get("states", [])
            if isinstance(state, dict)
            and state.get("attribute") == "visibility"
            and state.get("value") == "not_observed_current_frame"
        }
        uncertainty_items = {
            _slug(str(item.get("item")))
            for item in world_model.get("uncertainty", [])
            if isinstance(item, dict) and "not visible" in str(item.get("reason", "")).lower()
        }
        for name in not_currently_visible:
            normalized_name = _slug(name)
            if normalized_name in object_names or normalized_name in object_ids:
                if normalized_name not in visibility_states and normalized_name not in uncertainty_items:
                    errors.append(f"{name} is not visible in final frame but lacks visibility/uncertainty marker.")

    return errors


def _frame_observations(rows: List[Dict[str, Any]]) -> List[tuple[int, set[str]]]:
    frames: List[tuple[int, set[str]]] = []
    for row in rows:
        if row.get("event_type") != "world_model_update":
            continue
        update = row.get("model_update", {})
        if not isinstance(update, dict) or "frame_index" not in update:
            continue
        observed = {
            str(name)
            for name in update.get("observed_objects", [])
            if str(name).strip()
        }
        frames.append((int(update.get("frame_index", len(frames))), observed))
    return sorted(frames, key=lambda item: item[0])


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


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


def _read_jsonl(path: Path, errors: List[str]) -> List[Dict[str, Any]]:
    if not path.exists():
        errors.append(f"Missing episode log file: {path}")
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
        print("Visual sequence validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Visual sequence validation passed: {world_model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
