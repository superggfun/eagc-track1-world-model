from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GUARDRAILS = ["--episode-timeout-seconds", "600", "--max-qwen-calls-per-episode", "40"]
SOURCE_DIRS = [
    "clients",
    "env_adapters",
    "perception",
    "world_model",
    "planner",
    "executor",
    "logging_utils",
    "validators",
    "task_evaluator",
    "track1_runner",
    "scoring",
    "diagnostics",
    "tools",
    "tests",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run tiered EAGC Track 1 local test suites.")
    parser.add_argument("--tier", choices=["fast", "targeted", "standard", "full"], required=True)
    parser.add_argument("--seed", type=int, default=6)
    parser.add_argument("--difficulty", choices=["easy", "medium"], default="medium")
    args = parser.parse_args()

    commands = _commands(args.tier, args.seed, args.difficulty)
    for command in commands:
        print(f"\n$ {' '.join(command)}", flush=True)
        completed = subprocess.run(command, cwd=PROJECT_ROOT)
        if completed.returncode != 0:
            print(f"Command failed with exit code {completed.returncode}: {' '.join(command)}")
            return completed.returncode
    print(f"\nTest suite tier {args.tier!r} passed.")
    return 0


def _commands(tier: str, seed: int, difficulty: str) -> List[List[str]]:
    py = sys.executable
    compileall = [py, "-m", "compileall", *SOURCE_DIRS]
    smoke_mock = [py, "tests/smoke_test_all_mock_episodes.py", "--mode", "mock", "--all"]
    smoke_real = [py, "tests/smoke_test_all_mock_episodes.py", "--mode", "real", "--all", "--strict-real"]
    local_sim = [py, "tests/smoke_test_local_sim_episodes.py", "--mode", "real"]
    track1 = [py, "tests/smoke_test_track1_procedure.py", "--mode", "real"]
    visual_local_hybrid = [
        py,
        "tests/smoke_test_visual_local_hybrid.py",
        "--image-dir",
        "assets/test_sequences/bedroom_sequence",
        "--max-frames",
        "3",
    ]
    visual_sequence = [
        py,
        "tests/smoke_test_visual_sequence.py",
        "--image-dir",
        "assets/test_sequences/bedroom_sequence",
        "--max-frames",
        "3",
    ]
    generate_report = [py, "tools/generate_project_report.py"]
    targeted_replay = [
        py,
        "tools/replay_random_local_sim_failure.py",
        "--seed",
        str(seed),
        "--difficulty",
        difficulty,
        "--mode",
        "real",
    ]
    targeted_robustness = [
        py,
        "tests/robustness_test_random_local_sim.py",
        "--mode",
        "real",
        "--start-seed",
        str(seed),
        "--end-seed",
        str(seed),
        "--difficulty",
        difficulty,
        "--strict-leakage-check",
        *GUARDRAILS,
    ]
    easy20_mock = [
        py,
        "tests/robustness_test_random_local_sim.py",
        "--mode",
        "mock",
        "--num-episodes",
        "20",
        "--difficulty",
        "easy",
        "--strict-leakage-check",
        *GUARDRAILS,
    ]
    easy20_real = [
        py,
        "tests/robustness_test_random_local_sim.py",
        "--mode",
        "real",
        "--num-episodes",
        "20",
        "--difficulty",
        "easy",
        "--strict-leakage-check",
        *GUARDRAILS,
    ]
    medium5 = [
        py,
        "tests/robustness_test_random_local_sim.py",
        "--mode",
        "real",
        "--num-episodes",
        "5",
        "--difficulty",
        "medium",
        "--strict-leakage-check",
        *GUARDRAILS,
    ]
    easy100_mock = [
        py,
        "tests/robustness_test_random_local_sim.py",
        "--mode",
        "mock",
        "--num-episodes",
        "100",
        "--difficulty",
        "easy",
        "--strict-leakage-check",
        *GUARDRAILS,
    ]
    medium10_real = [
        py,
        "tests/robustness_test_random_local_sim.py",
        "--mode",
        "real",
        "--num-episodes",
        "10",
        "--difficulty",
        "medium",
        "--strict-leakage-check",
        *GUARDRAILS,
    ]

    if tier == "fast":
        commands = [compileall, smoke_mock]
        if _visual_sequence_available():
            commands.append(visual_local_hybrid)
        return commands
    if tier == "targeted":
        return [*_commands("fast", seed, difficulty), local_sim, track1, targeted_replay, targeted_robustness]
    if tier == "standard":
        return [compileall, smoke_real, local_sim, track1, easy20_mock, visual_sequence, generate_report]
    if tier == "full":
        return [*_commands("standard", seed, difficulty), easy100_mock, easy20_real, medium5, medium10_real]
    raise ValueError(f"Unknown tier: {tier}")


def _visual_sequence_available() -> bool:
    image_dir = PROJECT_ROOT / "assets" / "test_sequences" / "bedroom_sequence"
    if not image_dir.exists():
        return False
    return any(
        path.is_file()
        and path.name.lower().startswith("frame_")
        and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        for path in image_dir.iterdir()
    )


if __name__ == "__main__":
    raise SystemExit(main())
