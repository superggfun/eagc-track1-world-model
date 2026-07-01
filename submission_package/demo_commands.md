# Demo Commands

Run from the project root:

```powershell
cd <repo-root>
```

## Fast Gate

```powershell
python tools/run_test_suite.py --tier fast
```

## Targeted Gate

```powershell
python tools/run_test_suite.py --list-tiers
python tools/run_test_suite.py --tier targeted-text --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-local-sim --timeout-seconds 600
```

Aggregate targeted smoke is available, but may take several minutes:

```powershell
python tools/run_test_suite.py --tier targeted --timeout-seconds 900 --continue-on-failure
```

## Standard Gate

```powershell
python tools/run_test_suite.py --tier standard
```

## LocalSim Track 1 Demo

```powershell
python -m harness.run_track1 --env local_sim --episode-id local-explore-book-relocated --output-dir outputs/local_sim_track1_demo --validate
python -m harness.validate_outputs --output-dir outputs/local_sim_track1_demo --mode track1
```

Key outputs:

- `outputs/local_sim_track1_demo/world_model.json`
- `outputs/local_sim_track1_demo/episode_log.jsonl`
- `outputs/local_sim_track1_demo/run_audit.json`
- `outputs/local_sim_track1_demo/harness_result.json`
- `outputs/local_sim_track1_demo/track1_score.json`

## MazeSim Topology Stress Demo

```powershell
python tools/run_test_suite.py --tier targeted-maze --timeout-seconds 300
python tools/run_maze_stress_test.py --output-dir outputs/maze_stress
python -m validators.validate_maze_outputs --output-dir outputs/maze_stress --recursive
python tools/run_test_suite.py --tier targeted-maze-anti-loop --timeout-seconds 300
python tools/run_maze_anti_loop_test.py --output-dir outputs/maze_anti_loop
python -m validators.validate_maze_outputs --output-dir outputs/maze_anti_loop --recursive
```

Key outputs:

- `outputs/maze_stress/world_model.json`
- `outputs/maze_stress/episode_log.jsonl`
- `outputs/maze_stress/run_audit.json`
- `outputs/maze_stress/maze_metrics.json`
- `outputs/maze_stress/status.json`
- `outputs/maze_stress/reference_maze.json`
- `outputs/maze_stress/comparison_report.json`
- `outputs/maze_anti_loop/world_model.json`
- `outputs/maze_anti_loop/episode_log.jsonl`
- `outputs/maze_anti_loop/run_audit.json`
- `outputs/maze_anti_loop/maze_metrics.json`
- `outputs/maze_anti_loop/status.json`
- `outputs/maze_anti_loop/reference_maze.json`
- `outputs/maze_anti_loop/comparison_report.json`
- `outputs/maze_anti_loop/anti_loop_report.md`

Notes:

- `targeted-maze` is not part of the deterministic `fast` tier.
- MazeSim does not depend on an external simulator.
- MazeSim does not use Qwen/vLLM.
- MazeSim is a synthetic topology stress test, not an official EAGC runtime.
- `reference_maze.json` is a validation-only answer key; `world_model.json` is generated from agent observations and action results.
- Latest medium generated maze result: `success=True`, `goal_found=True`, `steps_taken=28`, `shortest_path_length=14`, `map_coverage=0.88`, `blocked_edges_encountered=2`, `replans=7`.
- The anti-loop tier adds loop lure, comb dead-end, blocked-shortcut, and unreachable-goal cases. The unreachable goal case is expected to fail gracefully with a non-empty termination reason rather than loop forever.
- Latest anti-loop results: `loop_lure_maze` succeeded in 8 steps; `dead_end_comb_maze` succeeded in 26 steps with `repeated_state_count=10` and `replans=10`; `blocked_shortcut_maze` succeeded in 11 steps with `blocked_edges_encountered=1` and `replans=2`; `unreachable_goal_maze` produced expected graceful failure with `goal_unreachable_or_budget_exhausted` in 3 steps.
- `dead_end_comb_maze` intentionally trades path length for dead-end discovery and recovery; the important signal is zero oscillation and eventual goal reach.
- `blocked_shortcut_maze` prioritizes safe recovery over exhaustive map completion, avoiding spurious edges while preserving high topology recall.
- `unreachable_goal_maze` records `expected_goal_reachable=false`, `goal_reached=false`, and `expected_outcome_met=true`.

## Visual Evidence Demo

```powershell
python -m harness.run_visual_demo --frames assets/test_sequences/bedroom_sequence --output-dir outputs/visual_evidence_demo --validate
python -m harness.validate_outputs --output-dir outputs/visual_evidence_demo --mode visual
```

Key outputs:

- `outputs/visual_evidence_demo/world_model.json`
- `outputs/visual_evidence_demo/episode_log.jsonl`
- `outputs/visual_evidence_demo/run_audit.json`
- `outputs/visual_evidence_demo/harness_result.json`
- `outputs/visual_evidence_demo/visual_task_result.json`

If local vLLM is unavailable, add `--mock` to the harness command for deterministic smoke mode.

## VirtualHome Manual-Play Evidence Demo

This is optional and is not part of the deterministic fast tier. It requires external VirtualHome resources and a manually running Windows simulator:

1. Start `VirtualHome.exe`.
2. Choose Windowed mode if prompted.
3. Click Play.
4. Confirm that `127.0.0.1:8080` is listening.

Then run:

```powershell
python tools/run_test_suite.py --tier targeted-virtualhome-manual --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-virtualhome-frame --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-virtualhome-vision --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-virtualhome-multiframe --timeout-seconds 600
python tools/build_virtualhome_evidence_report.py
```

Notes:

- These commands are not `fast` tier checks.
- The vision tiers require the already-running local Qwen/vLLM endpoint.
- They do not start lightweight vLLM.
- They do not modify, restart, or manage the existing Qwen Docker container.
- Generated frames, raw Qwen responses, and `outputs/virtualhome_spike/` artifacts are runtime outputs and should not be committed.

Resource profile:

```powershell
python tools/run_test_suite.py --tier targeted-resource-profile --timeout-seconds 300
```

This records current GPU/vLLM/VirtualHome coexistence status without starting lightweight vLLM and without managing the original Qwen Docker container.

Key outputs:

- `outputs/virtualhome_spike/scene_graph.json`
- `outputs/virtualhome_spike/program_log.json`
- `outputs/virtualhome_spike/converted_world_model.json`
- `outputs/virtualhome_spike/converted_episode_log.jsonl`
- `outputs/virtualhome_spike/frame_000.png`
- `outputs/virtualhome_spike/task_frames/`
- `outputs/virtualhome_spike/episode_visual_symbolic_comparison.json`

## Demo Snapshot

```powershell
python tools/create_demo_snapshot.py
```

Expected output:

- `outputs/demo_snapshot/local_sim_track1_demo/`
- `outputs/demo_snapshot/visual_evidence_demo/`
- `outputs/demo_snapshot/README_demo.md`

## Optional VirtualHome Multi-Room Exploration Evidence

Strict final live Windows runtime capture:

```powershell
python -m harness.run_virtualhome_continuous ^
  --virtualhome-exe "<YOUR_VIRTUALHOME_WINDOWS_EXEC_PATH>" ^
  --output-dir outputs/virtualhome_continuous ^
  --prediction-input-mode vlm_frame_extraction ^
  --max-steps 30 ^
  --target-room-coverage 0.8 ^
  --validate ^
  --final-submission
```

Replay validation from exported keyframes:

```powershell
python -m harness.run_virtualhome_replay ^
  --frames assets/test_sequences/virtualhome_exploration/frames ^
  --manifest assets/test_sequences/virtualhome_exploration/frame_manifest.json ^
  --output-dir outputs/virtualhome_exploration_replay ^
  --prediction-input-mode vlm_frame_extraction ^
  --validate
```

`mock_visual_extraction` is for CI/smoke only. The VirtualHome scene graph is used only as the reference answer key in `reference_world_model.json`, not to populate predicted `world_model.json`. These outputs are local evidence, not official hidden-evaluation scores.

Final bundle generation includes VirtualHome only when strict continuous closed-loop validation passes. Mock or replay output is copied, at most, under `optional_diagnostics/virtualhome_mock_replay/` and is not final Track 1 evidence.

## Report And Source Package

```powershell
python tools/generate_project_report.py
python tools/package_source.py
python tools/create_submission_bundle.py
python tools/pre_submission_audit.py
```

Expected output:

- `reports/v0.8.4_technical_report.md`
- `dist/source.zip`
