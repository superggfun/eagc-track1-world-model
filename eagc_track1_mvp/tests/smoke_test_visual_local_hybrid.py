from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from validators.validate_visual_local_hybrid import validate as validate_visual_local_hybrid
from validators.validate_visual_task_evidence import validate as validate_visual_task_evidence


TASKS = [
    ("Find the laptop.", "complete"),
    ("Identify where the book is.", "complete"),
    ("Is the laptop on the chair?", "uncertain"),
    ("Find the chair near the bed.", "uncertain"),
]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run visual-local hybrid smoke tasks.")
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--max-frames", type=int, default=3)
    args = parser.parse_args()

    image_dir = Path(args.image_dir)
    if not image_dir.is_absolute():
        image_dir = PROJECT_ROOT / image_dir
    if len(_frames(image_dir)) < 2:
        print(
            "Visual-local hybrid smoke requires at least 2 local images named "
            f"frame_000.jpg/png, frame_001.jpg/png, ... in {image_dir}."
        )
        return 1

    failures = 0
    for index, (task, expected_status) in enumerate(TASKS, start=1):
        output_dir = PROJECT_ROOT / "outputs" / "visual_local_hybrid_smoke" / f"task_{index:02d}"
        command = [
            sys.executable,
            "main.py",
            "--env",
            "visual_sequence",
            "--image-dir",
            str(image_dir),
            "--max-frames",
            str(args.max_frames),
            "--visual-local-hybrid",
            "--visual-task",
            task,
            "--output-dir",
            str(output_dir),
            "--validate",
        ]
        completed = subprocess.run(command, cwd=PROJECT_ROOT)
        if completed.returncode != 0:
            failures += 1
            print(f"task={task}")
            print(f"status=command_failed returncode={completed.returncode}")
            print(f"output_dir={output_dir}")
            continue

        world_model_path = output_dir / "world_model.json"
        audit_path = output_dir / "run_audit.json"
        episode_log_path = output_dir / "episode_log.jsonl"
        visual_task_result_path = output_dir / "visual_task_result.json"
        errors = validate_visual_local_hybrid(world_model_path, audit_path, episode_log_path)
        errors.extend(validate_visual_task_evidence(visual_task_result_path, audit_path))
        world_model = json.loads(world_model_path.read_text(encoding="utf-8"))
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        task_status = json.loads(visual_task_result_path.read_text(encoding="utf-8"))
        status = str(task_status.get("status", ""))
        supporting_count = len(task_status.get("supporting_evidence", []))
        contradicting_count = len(task_status.get("contradicting_evidence", []))
        missing_count = len(task_status.get("missing_evidence", []))
        if status != expected_status:
            errors.append(f"expected task_status={expected_status}, got {status}.")
        if expected_status == "complete" and supporting_count <= 0:
            errors.append("complete task requires supporting evidence.")
        if expected_status == "uncertain":
            answer = str(task_status.get("answer", "")).lower()
            if "cannot confirm" not in answer and "uncertain" not in answer:
                errors.append("uncertain task answer must clearly say the relation cannot be confirmed.")
            if missing_count <= 0:
                errors.append("uncertain task requires non-empty missing_evidence.")
        if errors:
            failures += 1
        print(f"task={task}")
        print(f"task_status={status}")
        print(f"confidence={task_status.get('confidence', 0.0)}")
        print(f"answer={task_status.get('answer', '')}")
        print(f"supporting_evidence_count={supporting_count}")
        print(f"contradicting_evidence_count={contradicting_count}")
        print(f"missing_evidence_count={missing_count}")
        print(f"evidence_summary={task_status.get('evidence_summary', '')}")
        print(f"object_count={len(world_model.get('objects', []))}")
        print(f"relation_count={len(world_model.get('relations', []))}")
        print(f"fallback_used={audit.get('fallback_used', False)}")
        print(f"unsupported_physical_action_count={audit.get('unsupported_physical_action_count', 0)}")
        print(f"output_dir={output_dir}")
        if errors:
            print("validation_errors=" + "; ".join(errors))
        print("")

    if failures:
        print(f"Visual-local hybrid smoke failed for {failures} task(s).")
        return 1
    print("Visual-local hybrid smoke passed.")
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
