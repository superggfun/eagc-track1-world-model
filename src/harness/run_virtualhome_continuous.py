from __future__ import annotations

import argparse
import os

from harness.virtualhome_exploration import (
    DEFAULT_CONTINUOUS_MAX_STEPS,
    DEFAULT_MAX_FALLBACKS,
    DEFAULT_PORT,
    DEFAULT_PREDICTION_INPUT_MODE,
    DEFAULT_TARGET_ROOM_COVERAGE,
    run_live,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run strict continuous closed-loop VirtualHome evidence.")
    parser.add_argument("--virtualhome-exe", default=os.environ.get("VIRTUALHOME_EXECUTABLE_PATH", ""))
    parser.add_argument("--attach-existing", action="store_true")
    parser.add_argument("--output-dir", default="outputs/virtualhome_continuous")
    parser.add_argument("--scene", type=int, default=0)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument(
        "--prediction-input-mode",
        default=DEFAULT_PREDICTION_INPUT_MODE,
        choices=["vlm_frame_extraction", "mock_visual_extraction", "manifest_action_trace"],
    )
    parser.add_argument("--max-steps", type=int, default=DEFAULT_CONTINUOUS_MAX_STEPS)
    parser.add_argument("--max-fallbacks", type=int, default=DEFAULT_MAX_FALLBACKS)
    parser.add_argument(
        "--target-room-coverage",
        type=float,
        default=DEFAULT_TARGET_ROOM_COVERAGE,
        help=(
            "Compatibility target for final validation/reporting. Continuous runtime stopping uses "
            "max steps and observation-derived frontier exhaustion, not a hard-coded room count."
        ),
    )
    parser.add_argument("--final-submission", action="store_true")
    parser.add_argument("--no-canonicalize", action="store_true")
    args = parser.parse_args(argv)
    return run_live(
        virtualhome_exe=args.virtualhome_exe or None,
        attach_existing=bool(args.attach_existing),
        output_dir=args.output_dir,
        scene=int(args.scene),
        port=int(args.port),
        validate=bool(args.validate),
        canonicalize=not bool(args.no_canonicalize),
        prediction_input_mode=str(args.prediction_input_mode),
        continuous_episode=True,
        max_steps=int(args.max_steps),
        target_room_coverage=float(args.target_room_coverage),
        max_fallbacks=int(args.max_fallbacks),
        final_submission=bool(args.final_submission),
    )


if __name__ == "__main__":
    raise SystemExit(main())
