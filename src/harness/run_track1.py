from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from entrypoints import main as project_main
from harness._common import elapsed, patch_audit, resolve_project_path, system_exit_code, write_harness_result
from harness.run_official import run_official
from harness.validate_outputs import validate_output_dir


def run_track1(
    *,
    env: str,
    episode_id: str,
    output_dir: str | Path,
    validate: bool,
    use_mock_llm: bool,
) -> int:
    if env == "official":
        return run_official(
            env="official",
            episode_id=episode_id,
            output_dir=output_dir,
            validate=validate,
            use_mock_llm=use_mock_llm,
        )
    if env != "local_sim":
        print("harness.run_track1 supports --env local_sim or --env official.", file=sys.stderr)
        return 2

    resolved_output_dir = resolve_project_path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    try:
        project_main.run_demo_from_config(
            project_main.DemoRunConfig(
                episode_id=episode_id,
                run_id=None,
                output_dir=resolved_output_dir,
                validate=validate,
                use_mock_llm=use_mock_llm,
                env=env,
                scene="FloorPlan1",
                vision=False,
                image_path=None,
                image_dir=None,
                max_steps=None,
                max_frames=None,
                visual_local_hybrid=False,
                visual_task=None,
                track1_procedure=True,
                seed=1,
                difficulty="easy",
            )
        )
    except SystemExit as exc:
        code = system_exit_code(exc)
        patch_audit(
            resolved_output_dir,
            {
                "success": False,
                "evidence_level": "closed_loop_final_evidence",
                "continuous_closed_loop": True,
                "capture_mode": "continuous_episode",
                "duration_seconds": elapsed(started),
                "errors": [str(exc) or f"run_track1 failed with exit code {code}"],
            },
        )
        write_harness_result(
            resolved_output_dir,
            mode="track1",
            success=False,
            validation_status={"passed": False, "errors": [str(exc) or f"run_track1 failed with exit code {code}"]},
            errors=[str(exc) or f"run_track1 failed with exit code {code}"],
            extra={"track1_score_path": "track1_score.json"},
        )
        return code or 1

    audit_updates: dict[str, Any] = {
        "success": True,
        "evidence_level": "closed_loop_final_evidence",
        "continuous_closed_loop": True,
        "capture_mode": "continuous_episode",
        "duration_seconds": elapsed(started),
        "errors": [],
        **({"qwen_response_summary_path": "", "debug_raw_path": ""} if use_mock_llm else {}),
    }
    patch_audit(resolved_output_dir, audit_updates)
    write_harness_result(
        resolved_output_dir,
        mode="track1",
        success=True,
        errors=[],
        extra={"track1_score_path": "track1_score.json"},
    )

    if validate:
        summary = validate_output_dir(resolved_output_dir, "track1")
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
            mode="track1",
            success=bool(summary["passed"]),
            validation_status=summary,
            errors=list(summary["errors"]),
            extra={"track1_score_path": "track1_score.json"},
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["passed"] else 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a reproducible Track 1 LocalSim sample or official adapter.")
    parser.add_argument("--env", default="local_sim", choices=["local_sim", "official"])
    parser.add_argument("--episode-id", default="local-explore-book-relocated")
    parser.add_argument("--output-dir", default="outputs/local_sim_track1_demo")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock LLM instead of local vLLM.")
    args = parser.parse_args(argv)

    return run_track1(
        env=args.env,
        episode_id=args.episode_id,
        output_dir=args.output_dir,
        validate=bool(args.validate),
        use_mock_llm=bool(args.mock),
    )




if __name__ == "__main__":
    raise SystemExit(main())
