# v0.17.6 Version Status: Final Submission Refresh After Maze Anti-Loop

v0.17.6 refreshes final submission materials after adding the MazeSim anti-loop and dead-end recovery stress test. It does not add new runtime functionality, train a model, run external simulators, start lightweight vLLM, or manage the local Qwen/vLLM Docker container.

## Maze Anti-Loop Purpose

The MazeSim anti-loop test is a synthetic topology robustness check for:

- loop avoidance
- dead-end recovery
- blocked-shortcut replanning
- unreachable-goal graceful termination
- repeated-state accounting
- no-progress termination

It complements the basic MazeSim topology stress test. It is not an official EAGC runtime, not official hidden evaluation, and not an official score.

## Validated Anti-Loop Result

`targeted-maze-anti-loop` passed. The latest validated cases produced:

- `loop_lure_maze`: success, goal_found, steps=8
- `dead_end_comb_maze`: success, goal_found, steps=26, repeated_state_count=10, replans=10
- `blocked_shortcut_maze`: success, goal_found, steps=11, blocked_edges_encountered=1, replans=2
- `unreachable_goal_maze`: expected graceful failure, terminated with `goal_unreachable_or_budget_exhausted`, steps=3

The runner writes:

- `outputs/maze_anti_loop/status.json`
- `outputs/maze_anti_loop/world_model.json`
- `outputs/maze_anti_loop/episode_log.jsonl`
- `outputs/maze_anti_loop/maze_metrics.json`
- `outputs/maze_anti_loop/anti_loop_report.md`

These are runtime artifacts and should not be committed.

## Updated Validated Components

- LocalSim Track 1 MVP
- Official-style Track1 procedure runner
- Visual-local hybrid evidence reporting
- VirtualHome real simulator manual-play evidence pipeline
- Qwen single-frame and multi-frame visual grounding
- ALFRED offline synthetic fixture adapter
- MazeSim basic topology stress test
- MazeSim anti-loop and dead-end recovery stress test
- Docker/source/submission package tooling

## Not Validated

- Official EAGC runtime
- Official hidden evaluation environments
- AI2-THOR / Habitat / ProcTHOR runtime execution
- Real ALFRED dataset conversion
- Fully automated VirtualHome startup
- Lightweight vLLM
- Model training or fine-tuning

## Refresh Scope

The v0.17.6 refresh updates:

- README
- technical report draft
- reproducibility statement
- demo commands
- submission checklist
- final artifact manifest
- final submission checklist
- pre-submission audit
- source package and submission bundle

## Expected Checks

```powershell
python -m compileall .
python tools/run_test_suite.py --tier fast
python tools/run_test_suite.py --tier targeted-text --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-maze --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-maze-anti-loop --timeout-seconds 300
python tools/pre_submission_audit.py
python tools/check_github_push_readiness.py
```

Do not run aggregate targeted, standard, full, VirtualHome, AI2-THOR, Habitat, ProcTHOR, lightweight vLLM, or training checks for this refresh.
