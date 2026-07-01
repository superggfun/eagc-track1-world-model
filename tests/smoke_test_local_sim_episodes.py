import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from validators.validate_episode_log import validate as validate_episode_log
from validators.validate_local_sim_run import validate as validate_local_sim_run
from validators.validate_semantic_consistency import validate as validate_semantic_consistency
from validators.validate_task_status import validate as validate_task_status
from validators.validate_world_model import validate as validate_world_model


EPISODES = [
    "local-explore-book-relocated",
    "local-door-locked-route",
    "local-container-unavailable",
    "local-tool-substitution",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all LocalSim smoke episodes.")
    parser.add_argument("--mode", choices=["real", "mock"], default="real")
    parser.add_argument("--episode-id", choices=EPISODES)
    args = parser.parse_args()

    episodes = [args.episode_id] if args.episode_id else EPISODES
    failures: List[str] = []
    for episode_id in episodes:
        output_dir = PROJECT_ROOT / "outputs" / "smoke" / "local_sim" / args.mode / episode_id
        output_dir.mkdir(parents=True, exist_ok=True)
        for artifact in ["world_model.json", "episode_log.jsonl", "run_audit.json"]:
            path = output_dir / artifact
            if path.exists():
                path.unlink()

        cmd = [
            sys.executable,
            "main.py",
            "--env",
            "local_sim",
            "--episode-id",
            episode_id,
            "--max-steps",
            "50",
            "--output-dir",
            str(output_dir),
            "--validate",
        ]
        if args.mode == "mock":
            cmd.append("--use-mock-llm")
        completed = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True, capture_output=True)
        if completed.returncode != 0:
            failures.append(f"{episode_id}: main.py failed\n{completed.stdout}\n{completed.stderr}")
            print(_summary_line(episode_id, "main_failed", 0, 0, 0, 0, output_dir))
            continue

        world_model_path = output_dir / "world_model.json"
        episode_log_path = output_dir / "episode_log.jsonl"
        audit_path = output_dir / "run_audit.json"
        validation_errors: List[str] = []
        for name, errors in {
            "world_model": validate_world_model(world_model_path),
            "semantic": validate_semantic_consistency(world_model_path),
            "episode_log": validate_episode_log(episode_log_path),
            "task_status": validate_task_status(world_model_path, episode_log_path),
            "local_sim": validate_local_sim_run(world_model_path, audit_path, episode_log_path),
        }.items():
            if errors:
                validation_errors.append(f"{name}: {errors}")

        world_model = _read_json(world_model_path)
        rows = _read_jsonl(episode_log_path)
        task_status = world_model.get("task_status", {}).get("status", "unknown")
        visited_rooms = world_model.get("visited_rooms", [])
        action_count = sum(1 for row in rows if row.get("event_type") in {"action", "resume_action", "recovery_action"})
        exception_count = len(world_model.get("exceptions", []))
        recovery_count = sum(1 for row in rows if row.get("event_type") == "recovery_action")
        print(
            _summary_line(
                episode_id,
                str(task_status),
                len(visited_rooms) if isinstance(visited_rooms, list) else 0,
                action_count,
                exception_count,
                recovery_count,
                output_dir,
            )
        )

        if validation_errors:
            failures.append(f"{episode_id}: validation failed\n" + "\n".join(validation_errors))

    if failures:
        print("\nLocalSim smoke failures:")
        for failure in failures:
            print(failure)
        return 1
    print("\nLocalSim smoke passed.")
    return 0


def _summary_line(
    episode_id: str,
    task_status: str,
    visited_rooms: int,
    action_count: int,
    exception_count: int,
    recovery_count: int,
    output_dir: Path,
) -> str:
    return (
        f"episode_id={episode_id} task_status={task_status} visited_rooms={visited_rooms} "
        f"action_count={action_count} exception_count={exception_count} "
        f"recovery_count={recovery_count} output_dir={output_dir}"
    )


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
