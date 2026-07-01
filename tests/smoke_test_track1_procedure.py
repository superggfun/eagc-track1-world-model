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
from validators.validate_track1_procedure import validate as validate_track1_procedure
from validators.validate_world_model import validate as validate_world_model


EPISODES = [
    "local-explore-book-relocated",
    "local-door-locked-route",
    "local-container-unavailable",
    "local-tool-substitution",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run official-style Track 1 procedure smoke tests.")
    parser.add_argument("--mode", choices=["real", "mock"], default="real")
    parser.add_argument("--episode-id", choices=EPISODES)
    args = parser.parse_args()

    failures: List[str] = []
    episodes = [args.episode_id] if args.episode_id else EPISODES
    for episode_id in episodes:
        output_dir = PROJECT_ROOT / "outputs" / "smoke" / "track1_procedure" / args.mode / episode_id
        output_dir.mkdir(parents=True, exist_ok=True)
        for artifact in ["world_model.json", "episode_log.jsonl", "run_audit.json", "track1_score.json"]:
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
            "--track1-procedure",
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
        audit_path = output_dir / "run_audit.json"
        episode_log_path = output_dir / "episode_log.jsonl"
        validation_errors: List[str] = []
        for name, errors in {
            "world_model": validate_world_model(world_model_path),
            "semantic": validate_semantic_consistency(world_model_path),
            "episode_log": validate_episode_log(episode_log_path),
            "task_status": validate_task_status(world_model_path, episode_log_path),
            "local_sim": validate_local_sim_run(world_model_path, audit_path, episode_log_path),
            "track1_procedure": validate_track1_procedure(world_model_path, audit_path, episode_log_path),
        }.items():
            if errors:
                validation_errors.append(f"{name}: {errors}")

        world_model = _read_json(world_model_path)
        audit = _read_json(audit_path)
        task_status = world_model.get("task_status", {}).get("status", "unknown")
        total_score = audit.get("track1_total_score", 0)
        print(
            _summary_line(
                episode_id,
                str(task_status),
                total_score,
                audit.get("exploration_steps_used", 0),
                audit.get("execution_steps_used", 0),
                audit.get("recovery_steps_used", 0),
                output_dir,
            )
        )
        if validation_errors:
            failures.append(f"{episode_id}: validation failed\n" + "\n".join(validation_errors))

    if failures:
        print("\nTrack 1 procedure smoke failures:")
        for failure in failures:
            print(failure)
        return 1
    print("\nTrack 1 procedure smoke passed.")
    return 0


def _summary_line(
    episode_id: str,
    task_status: str,
    total_score: Any,
    exploration_steps: Any,
    execution_steps: Any,
    recovery_steps: Any,
    output_dir: Path,
) -> str:
    return (
        f"episode_id={episode_id} task_status={task_status} total_score={total_score} "
        f"exploration_steps={exploration_steps} execution_steps={execution_steps} "
        f"recovery_steps={recovery_steps} output_dir={output_dir}"
    )


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
