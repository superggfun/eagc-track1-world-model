import json
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

    perception_count = sum(1 for row in rows if row.get("event_type") == "perception")
    update_count = sum(1 for row in rows if row.get("event_type") == "world_model_update")
    if perception_count < 2 or update_count < 2:
        errors.append("episode_log must contain multiple perception and world_model_update events.")

    objects = world_model.get("objects", [])
    if not isinstance(objects, list) or not objects:
        errors.append("world_model.objects must be non-empty for visual_sequence.")

    active_by_subject: Dict[str, List[Dict[str, Any]]] = {}
    for relation in world_model.get("relations", []):
        if (
            isinstance(relation, dict)
            and relation.get("status") == "active"
            and relation.get("relation") in LOCATION_RELATIONS
        ):
            active_by_subject.setdefault(str(relation.get("subject")), []).append(relation)
    for subject, relations in active_by_subject.items():
        if len(relations) > 1:
            rendered = [f"{rel.get('relation')} {rel.get('object')}" for rel in relations]
            errors.append(f"{subject} has multiple active location relations: {rendered}")

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
