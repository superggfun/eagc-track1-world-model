from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


REQUIRED_ANTI_LOOP_METRICS = {
    "loop_detected",
    "repeated_state_count",
    "max_visit_count_single_cell",
    "revisited_cells",
    "oscillation_count",
    "no_progress_windows",
    "coverage_plateau_steps",
    "terminated_by_budget",
    "terminated_reason",
    "unique_state_ratio",
    "dead_end_reentries",
    "blocked_edge_retries",
}
UNREACHABLE_EPISODES = {"unreachable_goal_maze"}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m validators.validate_maze_anti_loop_test outputs/maze_anti_loop/status.json")
        return 2
    status_path = Path(sys.argv[1])
    result = validate(status_path)
    if result["errors"]:
        print("Maze anti-loop validation failed:")
        for error in result["errors"]:
            print(f"- {error}")
        for warning in result["warnings"]:
            print(f"warning: {warning}")
        return 1
    print("Maze anti-loop validation passed.")
    for warning in result["warnings"]:
        print(f"warning: {warning}")
    return 0


def validate(status_path: Path) -> Dict[str, List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    if not status_path.exists():
        return {"errors": [f"Missing status file: {status_path}"], "warnings": warnings}
    status = _read_json(status_path, errors, "status")
    if not status:
        return {"errors": errors, "warnings": warnings}

    world_model_path = Path(status.get("world_model_path", status_path.parent / "world_model.json"))
    episode_log_path = Path(status.get("episode_log_path", status_path.parent / "episode_log.jsonl"))
    metrics_path = Path(status.get("maze_metrics_path", status_path.parent / "maze_metrics.json"))
    report_path = Path(status.get("anti_loop_report_path", status_path.parent / "anti_loop_report.md"))
    for label, path in [
        ("world_model", world_model_path),
        ("episode_log", episode_log_path),
        ("maze_metrics", metrics_path),
        ("anti_loop_report", report_path),
    ]:
        if not path.exists():
            errors.append(f"Missing {label}: {path}")

    metrics = _read_json(metrics_path, errors, "maze_metrics") if metrics_path.exists() else {}
    world_model = _read_json(world_model_path, errors, "world_model") if world_model_path.exists() else {}
    episodes = status.get("episodes", [])
    if not isinstance(episodes, list) or not episodes:
        errors.append("status.episodes must be a non-empty list")

    if world_model and world_model.get("source") != "maze_sim":
        errors.append("world_model.source must be maze_sim")
    if world_model and not world_model.get("topology"):
        errors.append("world_model.topology must be non-empty")
    if episode_log_path.exists() and not episode_log_path.read_text(encoding="utf-8").strip():
        errors.append("episode_log.jsonl must not be empty")

    if metrics:
        per_episode = metrics.get("episodes", {})
        if not isinstance(per_episode, dict) or not per_episode:
            errors.append("maze_metrics.episodes must be a non-empty object")

    for item in episodes:
        episode = item.get("episode", "")
        episode_metrics = item.get("metrics", {})
        missing = sorted(REQUIRED_ANTI_LOOP_METRICS - set(episode_metrics))
        if missing:
            errors.append(f"{episode}: missing anti-loop metrics: {missing}")
        if not item.get("terminated"):
            errors.append(f"{episode}: episode did not terminate")
        if not episode_metrics.get("terminated_reason"):
            errors.append(f"{episode}: terminated_reason is required")
        if episode in UNREACHABLE_EPISODES:
            if item.get("success"):
                errors.append(f"{episode}: unreachable episode should not report success")
            reason = str(episode_metrics.get("terminated_reason", ""))
            if "unreachable" not in reason and "budget" not in reason:
                errors.append(f"{episode}: expected graceful unreachable/budget termination, got {reason!r}")
        else:
            if not item.get("success") and not episode_metrics.get("terminated_reason"):
                errors.append(f"{episode}: reachable episode failed without reason")
        max_steps = int(episode_metrics.get("max_steps") or 0)
        max_visit = int(episode_metrics.get("max_visit_count_single_cell") or 0)
        if max_steps and max_visit > max_steps * 0.5:
            warnings.append(f"{episode}: max_visit_count_single_cell is high ({max_visit}/{max_steps})")
        oscillation_count = int(episode_metrics.get("oscillation_count") or 0)
        if oscillation_count > 10:
            warnings.append(f"{episode}: oscillation_count is high ({oscillation_count})")
        blocked_retries = int(episode_metrics.get("blocked_edge_retries") or 0)
        if blocked_retries > 3:
            warnings.append(f"{episode}: blocked_edge_retries is high ({blocked_retries})")

    return {"errors": errors, "warnings": warnings}


def _read_json(path: Path, errors: List[str], label: str) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Invalid {label} JSON: {exc}")
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
