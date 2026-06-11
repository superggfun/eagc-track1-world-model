# v0.17.5 Version Status: Maze Anti-Loop and Dead-End Recovery Stress

v0.17.5 adds synthetic MazeSim adversarial topology cases for anti-loop, dead-end recovery, blocked-shortcut replanning, and graceful unreachable-goal termination. It does not add external dependencies, train a model, run external simulators, start lightweight vLLM, or manage the local Qwen/vLLM Docker container.

## Purpose

The anti-loop stress test verifies whether the symbolic topology explorer can:

- avoid infinite ring/cycle wandering
- record repeated state visits
- recover from comb-style dead ends
- avoid repeatedly trying known blocked corridors
- terminate gracefully when the goal is unreachable
- report no-progress and loop metrics

This is a synthetic topology benchmark. It is not an official EAGC runtime, not official hidden evaluation, and not an official score.

## New Episodes

- `loop_lure_maze`: contains a ring/cycle lure and a goal outside the loop.
- `dead_end_comb_maze`: contains many comb-style dead-end branches.
- `blocked_shortcut_maze`: contains a tempting shortest path interrupted by blocked edges.
- `unreachable_goal_maze`: isolates the goal so graceful failure is expected.

## New Metrics

`outputs/maze_anti_loop/maze_metrics.json` records:

- `loop_detected`
- `repeated_state_count`
- `max_visit_count_single_cell`
- `revisited_cells`
- `oscillation_count`
- `no_progress_windows`
- `coverage_plateau_steps`
- `terminated_by_budget`
- `terminated_reason`
- `unique_state_ratio`
- `dead_end_reentries`
- `blocked_edge_retries`

## Outputs

- `outputs/maze_anti_loop/status.json`
- `outputs/maze_anti_loop/world_model.json`
- `outputs/maze_anti_loop/episode_log.jsonl`
- `outputs/maze_anti_loop/maze_metrics.json`
- `outputs/maze_anti_loop/anti_loop_report.md`

These are runtime artifacts and should not be committed.

## Validation Commands

```powershell
python -m compileall .
python tools/run_test_suite.py --tier fast
python tools/run_test_suite.py --tier targeted-maze --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-maze-anti-loop --timeout-seconds 300
python -m validators.validate_maze_anti_loop_test outputs/maze_anti_loop/status.json
```

Do not run aggregate targeted, standard, full, VirtualHome, AI2-THOR, Habitat, ProcTHOR, lightweight vLLM, or training checks for this release.
