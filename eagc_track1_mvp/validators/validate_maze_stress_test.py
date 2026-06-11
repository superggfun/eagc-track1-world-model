from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


REQUIRED_METRICS = {
    "success",
    "goal_found",
    "steps_taken",
    "shortest_path_length",
    "path_efficiency",
    "visited_cells",
    "total_cells",
    "map_coverage",
    "dead_ends_entered",
    "backtracks",
    "replans",
    "blocked_edges_encountered",
}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m validators.validate_maze_stress_test outputs/maze_stress/status.json")
        return 2
    status_path = Path(sys.argv[1])
    errors = validate(status_path)
    if errors:
        print("Maze stress validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Maze stress validation passed.")
    return 0


def validate(status_path: Path) -> List[str]:
    errors: List[str] = []
    if not status_path.exists():
        return [f"Missing status file: {status_path}"]
    status = _read_json(status_path, errors, "status")
    if not status:
        return errors
    world_model_path = Path(status.get("world_model_path", status_path.parent / "world_model.json"))
    episode_log_path = Path(status.get("episode_log_path", status_path.parent / "episode_log.jsonl"))
    metrics_path = Path(status.get("maze_metrics_path", status_path.parent / "maze_metrics.json"))

    for label, path in [("world_model", world_model_path), ("episode_log", episode_log_path), ("maze_metrics", metrics_path)]:
        if not path.exists():
            errors.append(f"Missing {label}: {path}")
    world_model = _read_json(world_model_path, errors, "world_model") if world_model_path.exists() else {}
    metrics = _read_json(metrics_path, errors, "maze_metrics") if metrics_path.exists() else {}

    if world_model:
        if world_model.get("source") != "maze_sim":
            errors.append("world_model.source must be maze_sim")
        if not world_model.get("topology"):
            errors.append("world_model.topology must be non-empty")
        if not world_model.get("cells"):
            errors.append("world_model.cells must be non-empty")
        if not world_model.get("edges"):
            errors.append("world_model.edges must be non-empty")
    if metrics:
        missing = sorted(REQUIRED_METRICS - set(metrics))
        if missing:
            errors.append(f"maze_metrics missing fields: {missing}")
        if metrics.get("success") is True and metrics.get("goal_found") is not True:
            errors.append("If success=true, goal_found must be true")
    if episode_log_path.exists() and not episode_log_path.read_text(encoding="utf-8").strip():
        errors.append("episode_log.jsonl must not be empty")
    return errors


def _read_json(path: Path, errors: List[str], label: str) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Invalid {label} JSON: {exc}")
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
