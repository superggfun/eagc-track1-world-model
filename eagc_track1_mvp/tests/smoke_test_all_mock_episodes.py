import argparse
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

OUTPUT_FILES = [
    "world_model.json",
    "episode_log.jsonl",
    "run_audit.json",
    "qwen_calls.jsonl",
    "debug_qwen_raw.txt",
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


if __name__ == "__main__":
    raise SystemExit(main())
