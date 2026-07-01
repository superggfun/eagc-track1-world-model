"""Shared utilities for harness runners."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from entrypoints import main as project_main
from audit.builder import to_artifact_relative_path
from harness.validate_outputs import PROJECT_ROOT


def elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 6)


def system_exit_code(exc: SystemExit) -> int:
    if isinstance(exc.code, int):
        return exc.code
    return 1


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def patch_audit(output_dir: Path, updates: dict[str, Any]) -> None:
    """Read run_audit.json, apply *updates*, write back."""
    audit_path = output_dir / "run_audit.json"
    audit: dict[str, Any] = {}
    if audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            audit = {}
    audit.update(updates)
    audit.setdefault("episode_id", "")
    audit.setdefault("validation_status", "not_requested")
    audit.setdefault("end_time", datetime.now(timezone.utc).isoformat())
    project_main.write_run_audit(audit_path, audit)


def write_harness_result(
    output_dir: Path,
    *,
    mode: str,
    success: bool,
    validation_status: Any = "not_requested",
    errors: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Write harness_result.json using artifact-relative paths only."""

    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "mode": mode,
        "success": success,
        "output_dir": ".",
        "world_model_path": "world_model.json",
        "episode_log_path": "episode_log.jsonl",
        "run_audit_path": "run_audit.json",
        "validation_status": validation_status,
        "errors": list(errors or []),
    }
    if extra:
        result.update(_relative_path_updates(extra, output_dir))
    project_main.write_run_audit(output_dir / "harness_result.json", result)


def _relative_path_updates(values: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    return {key: _relative_path_value(key, value, output_dir) for key, value in values.items()}


def _relative_path_value(key: str, value: Any, output_dir: Path) -> Any:
    if isinstance(value, dict):
        return _relative_path_updates(value, output_dir)
    if isinstance(value, list):
        return [_relative_path_value(key, item, output_dir) for item in value]
    if isinstance(value, Path):
        return to_artifact_relative_path(value, output_dir)
    if isinstance(value, str) and _is_path_key(key):
        return to_artifact_relative_path(value, output_dir) or value.replace("\\", "/")
    return value


def _is_path_key(key: str) -> bool:
    lowered = key.lower()
    return lowered.endswith(("_path", "_paths", "_dir")) or lowered == "output_dir"
