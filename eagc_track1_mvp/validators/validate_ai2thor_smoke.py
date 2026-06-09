import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def validate(world_model_path: Path, audit_path: Path) -> List[str]:
    errors: List[str] = []
    world_model = _read_json(world_model_path, errors, "world_model")
    audit = _read_json(audit_path, errors, "run_audit")
    if errors:
        return errors

    frame_path = Path(str(audit.get("simulator_frame_path", "")))
    metadata_path = Path(str(audit.get("simulator_metadata_path", "")))
    episode_log_path = Path(str(audit.get("episode_log_path", "")))

    if not frame_path.exists() or frame_path.stat().st_size == 0:
        errors.append(f"AI2-THOR frame file must exist and be non-empty: {frame_path}")
    if not metadata_path.exists() or metadata_path.stat().st_size == 0:
        errors.append(f"AI2-THOR metadata file must exist and be non-empty: {metadata_path}")
    else:
        _read_json(metadata_path, errors, "metadata")

    if audit.get("env") != "ai2thor":
        errors.append(f"run_audit.env must be 'ai2thor', got {audit.get('env')!r}.")
    if audit.get("vision_mode") is not True:
        errors.append("run_audit.vision_mode must be true for AI2-THOR smoke.")
    if audit.get("ai2thor_start_success") is not True:
        errors.append("run_audit.ai2thor_start_success must be true.")

    objects = world_model.get("objects", [])
    if not isinstance(objects, list) or not objects:
        errors.append("AI2-THOR vision world_model.objects must be non-empty.")

    if not episode_log_path.exists():
        errors.append(f"episode_log.jsonl must exist: {episode_log_path}")

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


def main() -> int:
    world_model_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/world_model.json")
    audit_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("outputs/run_audit.json")
    errors = validate(world_model_path, audit_path)
    if errors:
        print("AI2-THOR smoke validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"AI2-THOR smoke validation passed: {world_model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
