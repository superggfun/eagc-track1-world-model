from __future__ import annotations

import argparse

from harness.virtualhome_exploration import DEFAULT_PREDICTION_INPUT_MODE, run_replay


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay exported VirtualHome exploration keyframes and manifest.")
    parser.add_argument("--frames", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", default="outputs/virtualhome_exploration_replay")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument(
        "--prediction-input-mode",
        default=DEFAULT_PREDICTION_INPUT_MODE,
        choices=["vlm_frame_extraction", "mock_visual_extraction", "manifest_action_trace"],
    )
    parser.add_argument("--no-canonicalize", action="store_true")
    parser.add_argument("--final-submission", action="store_true")
    args = parser.parse_args(argv)
    return run_replay(
        frames=args.frames,
        manifest=args.manifest,
        output_dir=args.output_dir,
        validate=bool(args.validate),
        canonicalize=not bool(args.no_canonicalize),
        prediction_input_mode=str(args.prediction_input_mode),
        final_submission=bool(args.final_submission),
    )


if __name__ == "__main__":
    raise SystemExit(main())
