import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"
SMOKE_DIR = OUTPUT_DIR / "smoke"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

EPISODES = [
    "mock-bedroom-relocated",
    "mock-hallway-door-locked",
    "mock-kitchen-container-unavailable",
    "mock-study-tool-substitution",
    "mock-livingroom-nominal",
]

COMMANDS = [
    [sys.executable, "main.py"],
    [sys.executable, "-m", "validators.validate_world_model", "outputs/world_model.json"],
    [
        sys.executable,
        "-m",
        "validators.validate_semantic_consistency",
        "outputs/world_model.json",
    ],
    [sys.executable, "-m", "validators.validate_episode_log", "outputs/episode_log.jsonl"],
]


def main() -> int:
    original_config = CONFIG_PATH.read_text(encoding="utf-8")
    SMOKE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        for episode_id in EPISODES:
            print(f"\n=== Smoke episode: {episode_id} ===")
            _write_episode_config(original_config, episode_id)
            _clean_outputs()
            for command in COMMANDS:
                completed = subprocess.run(command, cwd=PROJECT_ROOT)
                if completed.returncode != 0:
                    return completed.returncode
            _archive_outputs(episode_id)
    finally:
        CONFIG_PATH.write_text(original_config, encoding="utf-8")
    print("\nAll mock episode smoke tests passed.")
    return 0


def _write_episode_config(original_config: str, episode_id: str) -> None:
    lines = []
    replaced = False
    for line in original_config.splitlines():
        if line.startswith("episode_id:"):
            lines.append(f"episode_id: {episode_id}")
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        lines.append(f"episode_id: {episode_id}")
    CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _clean_outputs() -> None:
    for name in ["world_model.json", "episode_log.jsonl", "debug_qwen_raw.txt"]:
        path = OUTPUT_DIR / name
        if path.exists():
            path.unlink()


def _archive_outputs(episode_id: str) -> None:
    episode_dir = SMOKE_DIR / episode_id
    if episode_dir.exists():
        shutil.rmtree(episode_dir)
    episode_dir.mkdir(parents=True)
    for name in ["world_model.json", "episode_log.jsonl", "debug_qwen_raw.txt"]:
        source = OUTPUT_DIR / name
        if source.exists():
            shutil.copy2(source, episode_dir / name)


if __name__ == "__main__":
    raise SystemExit(main())
