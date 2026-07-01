from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

from infra.paths import PROJECT_ROOT
from validators.validate_episode_log import validate as validate_episode_log
from validators.validate_local_sim_run import validate as validate_local_sim_run
from validators.validate_semantic_consistency import validate as validate_semantic_consistency
from validators.validate_task_status import validate as validate_task_status
from validators.validate_track1_procedure import validate as validate_track1_procedure
from validators.validate_visual_local_hybrid import validate as validate_visual_local_hybrid
from validators.validate_visual_sequence import validate as validate_visual_sequence
from validators.validate_visual_task_evidence import validate as validate_visual_task_evidence
from validators.validate_vision_extraction import validate as validate_vision_extraction
from validators.validate_world_model import validate as validate_world_model


PATH_KEYS = {
    "world_model_path",
    "episode_log_path",
    "run_audit_path",
    "track1_score_path",
    "visual_task_result_path",
    "qwen_response_summary_path",
}
LOCAL_ABSOLUTE_PATTERNS = [
    re.compile(r"[A-Za-z]:[\\/](?:Users|Documents|Windows|ProgramData|Temp|tmp)[\\/]", re.IGNORECASE),
    re.compile(r"/(?:Users|home|mnt/data|tmp)/"),
]


def validate_output_dir(output_dir: str | Path, mode: str) -> dict[str, Any]:
    """Validate a harness output directory and return a JSON-serializable summary."""

    resolved_output_dir = _resolve_output_dir(output_dir)
    errors: list[str] = []
    warnings: list[str] = []
    failed: list[str] = []

    world_model = _read_json_required(resolved_output_dir / "world_model.json", "world_model.json", errors, failed)
    rows = _read_jsonl_required(resolved_output_dir / "episode_log.jsonl", errors, failed)
    audit = _read_json_required(resolved_output_dir / "run_audit.json", "run_audit.json", errors, failed)
    harness_result = _read_json_required(
        resolved_output_dir / "harness_result.json",
        "harness_result.json",
        errors,
        failed,
    )

    if isinstance(world_model, dict):
        _validate_world_model_shape(world_model, errors, failed)
    if rows is not None and not rows:
        _add_failure(errors, failed, "episode_log_nonempty", "episode_log.jsonl must contain at least one JSON record.")
    if isinstance(audit, dict):
        _validate_audit_shape(audit, resolved_output_dir, errors, failed)
    if isinstance(harness_result, dict):
        _validate_harness_result_shape(harness_result, resolved_output_dir, errors, failed)

    if mode == "track1":
        _read_json_required(resolved_output_dir / "track1_score.json", "track1_score.json", errors, failed)
        if not errors:
            _extend_validator_errors(
                errors,
                failed,
                {
                    "world_model_validator": lambda: validate_world_model(resolved_output_dir / "world_model.json"),
                    "semantic_consistency": lambda: validate_semantic_consistency(resolved_output_dir / "world_model.json"),
                    "episode_log_validator": lambda: validate_episode_log(resolved_output_dir / "episode_log.jsonl"),
                    "task_status": lambda: validate_task_status(
                        resolved_output_dir / "world_model.json",
                        resolved_output_dir / "episode_log.jsonl",
                    ),
                    "local_sim": lambda: validate_local_sim_run(
                        resolved_output_dir / "world_model.json",
                        resolved_output_dir / "run_audit.json",
                        resolved_output_dir / "episode_log.jsonl",
                    ),
                    "track1_procedure": lambda: validate_track1_procedure(
                        resolved_output_dir / "world_model.json",
                        resolved_output_dir / "run_audit.json",
                        resolved_output_dir / "episode_log.jsonl",
                    ),
                },
            )
    elif mode == "official":
        if isinstance(audit, dict) and audit.get("env") != "official":
            _add_failure(
                errors,
                failed,
                "official_audit_env",
                f"Official output must have run_audit.env='official', got {audit.get('env')!r}.",
            )
        if isinstance(audit, dict) and audit.get("fallback_to_local_sim") is True:
            _add_failure(
                errors,
                failed,
                "official_no_fallback",
                "Official output must not fall back to LocalSim.",
            )
        if not errors:
            _extend_validator_errors(
                errors,
                failed,
                {
                    "world_model_validator": lambda: validate_world_model(resolved_output_dir / "world_model.json"),
                    "semantic_consistency": lambda: validate_semantic_consistency(resolved_output_dir / "world_model.json"),
                    "episode_log_validator": lambda: validate_episode_log(resolved_output_dir / "episode_log.jsonl"),
                    "task_status": lambda: validate_task_status(
                        resolved_output_dir / "world_model.json",
                        resolved_output_dir / "episode_log.jsonl",
                    ),
                },
            )
    elif mode == "visual":
        _read_json_required(resolved_output_dir / "visual_task_result.json", "visual_task_result.json", errors, failed)
        if isinstance(audit, dict):
            qwen_summary = str(audit.get("qwen_response_summary_path") or "").strip()
            if qwen_summary and not _resolve_audit_path(qwen_summary, resolved_output_dir).exists():
                _add_failure(
                    errors,
                    failed,
                    "qwen_response_summary_reference",
                    "run_audit.json references qwen_response_summary.json but the file is missing.",
                )
        if not errors:
            _extend_validator_errors(
                errors,
                failed,
                {
                    "world_model_validator": lambda: validate_world_model(resolved_output_dir / "world_model.json"),
                    "semantic_consistency": lambda: validate_semantic_consistency(resolved_output_dir / "world_model.json"),
                    "episode_log_validator": lambda: validate_episode_log(resolved_output_dir / "episode_log.jsonl"),
                    "vision_extraction": lambda: validate_vision_extraction(
                        resolved_output_dir / "world_model.json",
                        resolved_output_dir / "run_audit.json",
                    ),
                    "visual_sequence": lambda: validate_visual_sequence(
                        resolved_output_dir / "world_model.json",
                        resolved_output_dir / "run_audit.json",
                        resolved_output_dir / "episode_log.jsonl",
                    ),
                    "visual_local_hybrid": lambda: validate_visual_local_hybrid(
                        resolved_output_dir / "world_model.json",
                        resolved_output_dir / "run_audit.json",
                        resolved_output_dir / "episode_log.jsonl",
                    ),
                    "visual_task_evidence": lambda: validate_visual_task_evidence(
                        resolved_output_dir / "visual_task_result.json",
                        resolved_output_dir / "run_audit.json",
                    ),
                },
            )
    else:
        _add_failure(errors, failed, "mode", f"Unsupported validation mode: {mode}")

    failed = list(dict.fromkeys(failed))
    return {
        "passed": not errors,
        "failed": failed,
        "warnings": warnings,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate harness output artifacts.")
    parser.add_argument("--output-dir", required=True, help="Directory containing harness artifacts.")
    parser.add_argument("--mode", choices=["track1", "visual", "official"], required=True)
    args = parser.parse_args(argv)

    summary = validate_output_dir(args.output_dir, args.mode)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] else 1


def _resolve_output_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _read_json_required(path: Path, label: str, errors: list[str], failed: list[str]) -> dict[str, Any] | None:
    if not path.exists():
        _add_failure(errors, failed, label, f"Missing required artifact: {label}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _add_failure(errors, failed, label, f"{label} is not valid JSON: {exc}")
        return None
    if not isinstance(data, dict):
        _add_failure(errors, failed, label, f"{label} must be a JSON object.")
        return None
    return data


def _read_jsonl_required(path: Path, errors: list[str], failed: list[str]) -> list[dict[str, Any]] | None:
    if not path.exists():
        _add_failure(errors, failed, "episode_log.jsonl", "Missing required artifact: episode_log.jsonl")
        return None
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            _add_failure(errors, failed, "episode_log_jsonl", f"episode_log.jsonl line {line_number} is invalid JSON: {exc}")
            continue
        if not isinstance(row, dict):
            _add_failure(errors, failed, "episode_log_jsonl", f"episode_log.jsonl line {line_number} must be an object.")
            continue
        rows.append(row)
    return rows


def _validate_world_model_shape(world_model: dict[str, Any], errors: list[str], failed: list[str]) -> None:
    candidate_fields = ["objects", "relations", "topology", "states"]
    if not any(isinstance(world_model.get(field), list) and world_model.get(field) for field in candidate_fields):
        _add_failure(
            errors,
            failed,
            "world_model_basic_content",
            "world_model.json must contain at least one non-empty objects/relations/topology/states list.",
        )


def _validate_audit_shape(audit: dict[str, Any], output_dir: Path, errors: list[str], failed: list[str]) -> None:
    required_fields = [
        "start_time",
        "end_time",
        "duration_seconds",
        "episode_id",
        "env",
        "success",
        "validation_status",
        "errors",
    ]
    for field in required_fields:
        if field not in audit:
            _add_failure(errors, failed, "run_audit_required_fields", f"run_audit.json missing required field: {field}")

    offenders = _absolute_path_values(audit)
    for key_path, value in offenders:
        _add_failure(
            errors,
            failed,
            "run_audit_no_absolute_paths",
            f"run_audit.json contains local absolute path at {key_path}: {value}",
        )

    for key in PATH_KEYS:
        raw = str(audit.get(key) or "").strip()
        if not raw:
            continue
        if key == "qwen_response_summary_path":
            continue
        if not _resolve_audit_path(raw, output_dir).exists():
            _add_failure(errors, failed, key, f"run_audit.{key} references a missing file: {raw}")


def _validate_harness_result_shape(
    result: dict[str, Any],
    output_dir: Path,
    errors: list[str],
    failed: list[str],
) -> None:
    required_fields = [
        "mode",
        "success",
        "output_dir",
        "world_model_path",
        "episode_log_path",
        "run_audit_path",
        "validation_status",
        "errors",
    ]
    for field in required_fields:
        if field not in result:
            _add_failure(errors, failed, "harness_result_required_fields", f"harness_result.json missing required field: {field}")

    offenders = _absolute_path_values(result)
    for key_path, value in offenders:
        _add_failure(
            errors,
            failed,
            "harness_result_no_absolute_paths",
            f"harness_result.json contains local absolute path at {key_path}: {value}",
        )

    if result.get("output_dir") != ".":
        _add_failure(errors, failed, "harness_result_output_dir", "harness_result.output_dir must be '.'.")

    for key in PATH_KEYS:
        raw = str(result.get(key) or "").strip()
        if not raw:
            continue
        if key == "qwen_response_summary_path":
            continue
        if not _resolve_audit_path(raw, output_dir).exists():
            _add_failure(errors, failed, key, f"harness_result.{key} references a missing file: {raw}")


def _extend_validator_errors(
    errors: list[str],
    failed: list[str],
    validators: dict[str, Callable[[], list[str]]],
) -> None:
    for name, validator in validators.items():
        validator_errors = validator()
        if not validator_errors:
            continue
        failed.append(name)
        for error in validator_errors:
            errors.append(f"{name}: {error}")


def _absolute_path_values(value: Any, key_path: str = "$") -> list[tuple[str, str]]:
    offenders: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            offenders.extend(_absolute_path_values(child, f"{key_path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            offenders.extend(_absolute_path_values(child, f"{key_path}[{index}]"))
    elif isinstance(value, str) and _contains_local_absolute_path(value):
        offenders.append((key_path, value))
    return offenders


def _contains_local_absolute_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return any(pattern.search(normalized) for pattern in LOCAL_ABSOLUTE_PATTERNS)


def _resolve_audit_path(value: str, output_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return output_dir / path


def _add_failure(errors: list[str], failed: list[str], check: str, message: str) -> None:
    failed.append(check)
    errors.append(message)


if __name__ == "__main__":
    raise SystemExit(main())
