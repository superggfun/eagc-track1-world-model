from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from entrypoints import main as project_main
from harness._common import elapsed, patch_audit, resolve_project_path, system_exit_code, write_harness_result
from harness.validate_outputs import validate_output_dir


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def run_visual_demo(
    *,
    frames: str | Path,
    output_dir: str | Path,
    validate: bool,
    use_mock_llm: bool,
    max_frames: int,
    visual_task: str,
) -> int:
    resolved_frames = resolve_project_path(frames)
    resolved_output_dir = resolve_project_path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    frame_paths = _frames(resolved_frames)
    if not frame_paths:
        message = (
            f"No visual demo frames found in {resolved_frames}. "
            "Expected local files named frame_000.png/frame_000.jpg, frame_001.png/frame_001.jpg, ..."
        )
        print(message, file=sys.stderr)
        _write_failure_audit(resolved_output_dir, resolved_frames, started, message)
        write_harness_result(
            resolved_output_dir,
            mode="visual",
            success=False,
            validation_status={"passed": False, "errors": [message]},
            errors=[message],
            extra={
                "visual_task_result_path": "visual_task_result.json",
                "image_dir": resolved_frames,
            },
        )
        return 1

    try:
        project_main.run_demo_from_config(
            project_main.DemoRunConfig(
                episode_id=None,
                run_id=None,
                output_dir=resolved_output_dir,
                validate=validate,
                use_mock_llm=use_mock_llm,
                env="visual_sequence",
                scene="",
                vision=False,
                image_path=None,
                image_dir=str(resolved_frames),
                max_steps=None,
                max_frames=max_frames,
                visual_local_hybrid=True,
                visual_task=visual_task,
                track1_procedure=False,
                seed=1,
                difficulty="easy",
            )
        )
    except SystemExit as exc:
        code = system_exit_code(exc)
        help_text = ""
        if not use_mock_llm:
            help_text = (
                " If this failed because local vLLM is not running, start the configured "
                "OpenAI-compatible endpoint or rerun with --mock for deterministic smoke mode."
            )
            print(help_text.strip(), file=sys.stderr)
        patch_audit(
            resolved_output_dir,
            {
                "success": False,
                "duration_seconds": elapsed(started),
                "errors": [(str(exc) or f"run_visual_demo failed with exit code {code}") + help_text],
            },
        )
        error = (str(exc) or f"run_visual_demo failed with exit code {code}") + help_text
        write_harness_result(
            resolved_output_dir,
            mode="visual",
            success=False,
            validation_status={"passed": False, "errors": [error]},
            errors=[error],
            extra={
                "visual_task_result_path": "visual_task_result.json",
                "image_dir": resolved_frames,
            },
        )
        return code or 1

    patch_audit(
        resolved_output_dir,
        {
            "success": True,
            "duration_seconds": elapsed(started),
            "errors": [],
            **({"qwen_response_summary_path": "", "debug_raw_path": ""} if use_mock_llm else {}),
        },
    )
    write_harness_result(
        resolved_output_dir,
        mode="visual",
        success=True,
        errors=[],
        extra={
            "visual_task_result_path": "visual_task_result.json",
            "image_dir": resolved_frames,
        },
    )

    if validate:
        summary = validate_output_dir(resolved_output_dir, "visual")
        patch_audit(
            resolved_output_dir,
            {
                "success": bool(summary["passed"]),
                "validation_status": summary,
                "errors": list(summary["errors"]),
                "duration_seconds": elapsed(started),
            },
        )
        write_harness_result(
            resolved_output_dir,
            mode="visual",
            success=bool(summary["passed"]),
            validation_status=summary,
            errors=list(summary["errors"]),
            extra={
                "visual_task_result_path": "visual_task_result.json",
                "image_dir": resolved_frames,
            },
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["passed"] else 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a reproducible visual evidence sample.")
    parser.add_argument("--frames", required=True, help="Directory containing frame_*.png/jpg images.")
    parser.add_argument("--output-dir", default="outputs/visual_evidence_demo")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock vision extraction.")
    parser.add_argument("--max-frames", type=int, default=3)
    parser.add_argument("--visual-task", default="Is the laptop on the chair?")
    args = parser.parse_args(argv)

    return run_visual_demo(
        frames=args.frames,
        output_dir=args.output_dir,
        validate=bool(args.validate),
        use_mock_llm=bool(args.mock),
        max_frames=max(1, int(args.max_frames)),
        visual_task=str(args.visual_task),
    )


def _write_failure_audit(output_dir: Path, frames: Path, started: float, message: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    audit = {
        "start_time": now,
        "end_time": now,
        "duration_seconds": elapsed(started),
        "episode_id": f"visual-sequence-{frames.name or 'frames'}",
        "env": "visual_sequence",
        "success": False,
        "validation_status": {"passed": False, "errors": [message]},
        "errors": [message],
        "fallback_used": False,
        "vision_call_success": False,
        "qwen_call_success_count": 0,
        "image_dir": frames,
    }
    project_main.write_run_audit(output_dir / "run_audit.json", audit)


def _frames(image_dir: Path) -> list[Path]:
    if not image_dir.exists() or not image_dir.is_dir():
        return []
    return sorted(
        [
            path
            for path in image_dir.iterdir()
            if path.is_file() and path.name.lower().startswith("frame_") and path.suffix.lower() in IMAGE_SUFFIXES
        ],
        key=lambda path: path.name.lower(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
