import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"
SMOKE_DIR = OUTPUT_DIR / "smoke"

EPISODES = [
    "mock-bedroom-relocated",
    "mock-hallway-door-locked",
    "mock-kitchen-container-unavailable",
    "mock-study-tool-substitution",
    "mock-livingroom-nominal",
]

EXCEPTION_EPISODES = {
    "mock-bedroom-relocated": "object_relocated",
    "mock-hallway-door-locked": "door_locked",
    "mock-kitchen-container-unavailable": "target_container_unavailable",
    "mock-study-tool-substitution": "tool_substitution",
}
EXPECTED_TASK_STATUS = {
    "mock-bedroom-relocated": "complete",
    "mock-hallway-door-locked": "complete",
    "mock-kitchen-container-unavailable": "blocked_recovered",
    "mock-study-tool-substitution": "complete",
    "mock-livingroom-nominal": "complete",
}

OUTPUT_FILES = [
    "world_model.json",
    "episode_log.jsonl",
    "run_audit.json",
    "qwen_calls.jsonl",
    "debug_qwen_raw.txt",
]

VALIDATOR_COMMANDS = [
    [sys.executable, "-m", "validators.validate_world_model", "outputs/world_model.json"],
    [
        sys.executable,
        "-m",
        "validators.validate_semantic_consistency",
        "outputs/world_model.json",
    ],
    [sys.executable, "-m", "validators.validate_episode_log", "outputs/episode_log.jsonl"],
    [
        sys.executable,
        "-m",
        "validators.validate_task_status",
        "outputs/world_model.json",
        "outputs/episode_log.jsonl",
    ],
]


def main() -> int:
    args = parse_args()
    modes = ["mock", "real"] if args.mode == "both" else [args.mode]
    SMOKE_DIR.mkdir(parents=True, exist_ok=True)
    for mode in modes:
        for episode_id in EPISODES:
            print(f"\n=== Smoke mode={mode} episode={episode_id} ===")
            _clean_outputs()
            command = [sys.executable, "main.py", "--episode-id", episode_id, "--validate"]
            if mode == "mock":
                command.append("--use-mock-llm")
            completed = subprocess.run(command, cwd=PROJECT_ROOT)
            if completed.returncode != 0:
                return completed.returncode
            for validator_command in VALIDATOR_COMMANDS:
                completed = subprocess.run(validator_command, cwd=PROJECT_ROOT)
                if completed.returncode != 0:
                    return completed.returncode
            expectation_error = _check_recovery_expectations(episode_id)
            if expectation_error:
                print(expectation_error)
                return 1
            task_status_error = _check_task_status(episode_id)
            if task_status_error:
                print(task_status_error)
                return 1
            _archive_outputs(mode, episode_id)
    print("\nAll requested mock episode smoke tests passed.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all mock episodes through validators.")
    parser.add_argument(
        "--mode",
        choices=["mock", "real", "both"],
        default="mock",
        help="mock is deterministic and default; real calls local vLLM.",
    )
    parser.add_argument("--real-vllm", action="store_true", help="Alias for --mode real.")
    parser.add_argument("--both", action="store_true", help="Alias for --mode both.")
    args = parser.parse_args()
    if args.real_vllm:
        args.mode = "real"
    if args.both:
        args.mode = "both"
    return args


def _clean_outputs() -> None:
    for name in OUTPUT_FILES:
        path = OUTPUT_DIR / name
        if path.exists():
            path.unlink()


def _archive_outputs(mode: str, episode_id: str) -> None:
    episode_dir = SMOKE_DIR / mode / episode_id
    if episode_dir.exists():
        shutil.rmtree(episode_dir)
    episode_dir.mkdir(parents=True)
    for name in OUTPUT_FILES:
        source = OUTPUT_DIR / name
        if source.exists():
            shutil.copy2(source, episode_dir / name)


def _check_recovery_expectations(episode_id: str) -> str:
    log_path = OUTPUT_DIR / "episode_log.jsonl"
    world_model_path = OUTPUT_DIR / "world_model.json"
    rows = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    event_types = [row.get("event_type") for row in rows]
    if episode_id in EXCEPTION_EPISODES:
        expected_type = EXCEPTION_EPISODES[episode_id]
        world_model = json.loads(world_model_path.read_text(encoding="utf-8"))
        exception_types = [
            item.get("exception", {}).get("type")
            for item in world_model.get("exceptions", [])
            if isinstance(item, dict)
        ]
        if expected_type not in exception_types:
            return f"{episode_id} missing expected exception type {expected_type}."
        if "replanning" not in event_types:
            return f"{episode_id} missing replanning event."
        if not any(event in event_types for event in ["recovery_action", "recovery_complete"]):
            return f"{episode_id} missing recovery_action or recovery_complete event."
    return ""


def _check_task_status(episode_id: str) -> str:
    world_model_path = OUTPUT_DIR / "world_model.json"
    world_model = json.loads(world_model_path.read_text(encoding="utf-8"))
    task_status = world_model.get("task_status", {})
    status = task_status.get("status")
    success = task_status.get("success")
    reason = task_status.get("reason")
    print(f"task_status episode={episode_id} status={status} success={success} reason={reason}")
    expected = EXPECTED_TASK_STATUS[episode_id]
    if status != expected:
        return f"{episode_id} expected task_status {expected}, got {status}."
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
