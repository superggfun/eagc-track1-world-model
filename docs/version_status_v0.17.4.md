# v0.17.4 Version Status: Final Submission Refresh After MazeSim

v0.17.4 refreshes final submission materials after adding the MazeSim topology stress benchmark. It does not add new runtime functionality, train a model, run external simulators, start lightweight vLLM, or manage the local Qwen/vLLM Docker container.

## MazeSim Purpose

MazeSim is a synthetic topology stress test for:

- exploration under unknown topology
- incremental topology mapping
- dead-end handling
- blocked-corridor recovery
- replanning
- hidden-goal search

It complements the VirtualHome evidence pipeline. VirtualHome stresses household scene graph, action program, frame export, and visual grounding; MazeSim stresses topology exploration and planning. MazeSim is not an official EAGC runtime and should not be described as official hidden evaluation.

## Validated Maze Result

`targeted-maze` passed. The medium generated maze produced:

- success: `true`
- goal_found: `true`
- steps_taken: `28`
- shortest_path_length: `14`
- map_coverage: `0.88`
- blocked_edges_encountered: `2`
- replans: `7`

The runner writes:

- `outputs/maze_stress/world_model.json`
- `outputs/maze_stress/episode_log.jsonl`
- `outputs/maze_stress/maze_metrics.json`
- `outputs/maze_stress/status.json`

These are runtime artifacts and should not be committed.

## Overall Validated Components

- LocalSim Track 1 MVP
- Official-style Track1 procedure runner
- Visual-local hybrid evidence reporting
- VirtualHome real simulator manual-play pipeline
- ALFRED offline synthetic fixture conversion
- MazeSim synthetic topology stress test
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

The v0.17.4 refresh updates:

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
python tools/pre_submission_audit.py
python tools/check_github_push_readiness.py
```

Do not run aggregate targeted, standard, full, VirtualHome, AI2-THOR, Habitat, ProcTHOR, or training checks for this refresh.
