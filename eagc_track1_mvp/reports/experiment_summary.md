# Experiment Summary

The current experiments are local robustness checks for the Track 1 MVP. They are not official EAGC results.

## Fixed LocalSim Episodes

Fixed LocalSim episodes cover known exception types and expected statuses:

- `local-explore-book-relocated`: object relocation recovery, expected `complete`.
- `local-door-locked-route`: locked route recovery, expected `complete`.
- `local-container-unavailable`: fallback target recovery, expected `blocked_recovered`.
- `local-tool-substitution`: tool substitution recovery, expected `complete`.

## Randomized LocalSim Episodes

Randomized runs use generated hidden-style episode specs. The agent receives only public environment information and task observations. Evaluator-only fields such as success conditions, expected statuses, hidden relocation targets, and controlled exception definitions are kept out of prompts, logs, and world model state.

Difficulty levels:

- `easy`: sanity check for generator, planner, validator, and scoring behavior.
- `medium`: local robustness check with harder object locations, door locks, unavailable targets, tool candidates, distractors, and limited unrecoverable cases.

## Current Gate

Development gates used for v0.8.x:

- fast: compile and mock smoke tests.
- targeted: replay and robustness check for a known seed.
- standard: real Qwen smoke tests, fixed LocalSim, Track 1 procedure, and a small medium robustness batch.
- full: larger mock/real randomized robustness suite.

The local score is `local_heuristic_score`. It is not an official Track 1 score.

## Visual Sequence Smoke Validation

v0.9.1 adds a finalized local real-image visual sequence smoke validation. The run used three local Pexels bedroom images under `assets/test_sequences/bedroom_sequence/`, named `frame_000.jpg`, `frame_001.jpg`, and `frame_002.jpg`.

Observed validation summary:

- `processed_frames=3`
- `qwen_call_count=3`
- `fallback_used=False`
- `vision_parse_success=True`
- `object_count=15`
- `relation_count=23`

The run validated object persistence across frames, `not_observed_current_frame` visibility records for temporarily missing objects, and stale/active relation updates when spatial relations changed.

Object and relation counts can vary slightly across real Qwen vision runs, so the smoke gate treats structural consistency and temporal world-model behavior as the stable validation targets.

This is a local visual sequence smoke test only. It is not an official environment, not ProcTHOR/AI2-THOR, and not model training. The Pexels frame images are local test resources and are not included in git.
