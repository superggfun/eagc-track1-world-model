from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from validators.validate_visual_sequence import validate as validate_visual_sequence


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run visual sequence smoke test.")
    parser.add_argument("--image-dir", required=True, help="Directory containing frame_000.jpg/png style images.")
    parser.add_argument("--max-frames", type=int, default=3)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    image_dir = Path(args.image_dir)
    if not image_dir.is_absolute():
        image_dir = project_root / image_dir

    frames = _frames(image_dir)
    if len(frames) < 2:
        print(
            "Visual sequence smoke requires at least 2 local images named frame_000.jpg/png, "
            f"frame_001.jpg/png, ... in {image_dir}."
        )
        return 1

    output_dir = project_root / "outputs" / "visual_sequence_smoke" / image_dir.name
    command = [
        sys.executable,
        "main.py",
        "--env",
        "visual_sequence",
        "--image-dir",
        str(image_dir),
        "--max-frames",
        str(args.max_frames),
        "--output-dir",
        str(output_dir),
        "--validate",
    ]
    completed = subprocess.run(command, cwd=project_root)
    if completed.returncode != 0:
        return completed.returncode

    world_model_path = output_dir / "world_model.json"
    audit_path = output_dir / "run_audit.json"
    episode_log_path = output_dir / "episode_log.jsonl"
    errors = validate_visual_sequence(world_model_path, audit_path, episode_log_path)
    if errors:
        print("Visual sequence smoke validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    world_model = json.loads(world_model_path.read_text(encoding="utf-8"))
    print("Visual sequence smoke passed.")
    print(f"processed_frames={len(audit.get('processed_frames', []))}")
    print(f"qwen_call_count={audit.get('qwen_call_count', 0)}")
    print(f"object_count={len(world_model.get('objects', []))}")
    print(f"relation_count={len(world_model.get('relations', []))}")
    print(f"fallback_used={audit.get('fallback_used', False)}")
    print(f"output_dir={output_dir}")
    return 0


def _frames(image_dir: Path) -> list[Path]:
    if not image_dir.exists() or not image_dir.is_dir():
        return []
    return sorted(
        [
            path
            for path in image_dir.iterdir()
            if path.is_file()
            and path.name.lower().startswith("frame_")
            and path.suffix.lower() in IMAGE_SUFFIXES
        ],
        key=lambda path: path.name.lower(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
