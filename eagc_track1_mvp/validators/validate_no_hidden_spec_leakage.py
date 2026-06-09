import json
import sys
from pathlib import Path
from typing import Any, Dict, List


FORBIDDEN_FIELD_NAMES = {
    "success_condition",
    "expected_task_status",
    "controlled_exception",
    "hidden_spec",
    "hidden_object_relocation_target",
    "evaluator_only",
    "to_room",
    "to_region",
    "to_support",
}


def validate(world_model_path: Path, audit_path: Path, episode_log_path: Path) -> List[str]:
    errors: List[str] = []
    audit = _read_json(audit_path, errors, "run_audit")
    if errors:
        return errors
    spec_path = Path(str(audit.get("generated_episode_spec_path", "")))
    spec = _read_json(spec_path, errors, "generated_episode_spec") if spec_path.exists() else {}
    hidden_spec = spec.get("hidden_spec", {}) if isinstance(spec, dict) else {}
    if not isinstance(hidden_spec, dict):
        hidden_spec = {}

    agent_visible_paths = [
        world_model_path,
        episode_log_path,
        Path(str(audit.get("qwen_response_summary_path", ""))),
        Path(str(audit.get("output_dir", ""))) / "qwen_calls.jsonl",
    ]
    for path in agent_visible_paths:
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        errors.extend(_check_forbidden_field_names(path, text))
        errors.extend(_check_raw_hidden_payload(path, text, hidden_spec))

    errors.extend(_check_controlled_exception_timing(episode_log_path))
    return errors


def _check_forbidden_field_names(path: Path, text: str) -> List[str]:
    errors: List[str] = []
    for field in sorted(FORBIDDEN_FIELD_NAMES):
        if f'"{field}"' in text or f"'{field}'" in text:
            errors.append(f"{path} contains hidden field name {field!r}.")
    return errors


def _check_raw_hidden_payload(path: Path, text: str, hidden_spec: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not hidden_spec:
        return errors
    raw_hidden = json.dumps(hidden_spec, sort_keys=True, ensure_ascii=False)
    normalized_text = " ".join(text.split())
    if raw_hidden and raw_hidden in normalized_text:
        errors.append(f"{path} appears to contain raw hidden_spec payload.")
    return errors


def _check_controlled_exception_timing(episode_log_path: Path) -> List[str]:
    if not episode_log_path.exists():
        return []
    errors: List[str] = []
    seen_exception = False
    for line_number, line in enumerate(episode_log_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = json.dumps(row, ensure_ascii=False)
        if not seen_exception and '"exception"' in text and row.get("event_type") not in {"execution_exception", "replanning"}:
            if any(token in text for token in ['"likely_locations"', '"prior_support"', '"prior_region"']):
                errors.append(f"episode_log line {line_number} records exception details before execution_exception.")
        if row.get("event_type") == "execution_exception":
            seen_exception = True
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
    world_model_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/world_model.json")
    audit_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("outputs/run_audit.json")
    episode_log_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("outputs/episode_log.jsonl")
    errors = validate(world_model_path, audit_path, episode_log_path)
    if errors:
        print("Hidden spec leakage validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Hidden spec leakage validation passed: {world_model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
