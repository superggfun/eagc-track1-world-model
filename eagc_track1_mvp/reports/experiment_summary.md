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

