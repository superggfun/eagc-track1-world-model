# Demo Commands

Run from the project root:

```powershell
cd "C:\Users\Alphay\Documents\New project\eagc_track1_mvp"
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
python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
```

Key outputs:

- `outputs/world_model.json`
- `outputs/episode_log.jsonl`
- `outputs/run_audit.json`
- `track1_score.json` in the isolated run directory

## MazeSim Topology Stress Demo

```powershell
python tools/run_test_suite.py --tier targeted-maze --timeout-seconds 300
python -m validators.validate_maze_stress_test outputs/maze_stress/status.json
```

Key outputs:

- `outputs/maze_stress/world_model.json`
- `outputs/maze_stress/episode_log.jsonl`
- `outputs/maze_stress/maze_metrics.json`
- `outputs/maze_stress/status.json`

Notes:

- `targeted-maze` is not part of the deterministic `fast` tier.
- MazeSim does not depend on an external simulator.
- MazeSim does not use Qwen/vLLM.
- MazeSim is a synthetic topology stress test, not an official EAGC runtime.
- Latest medium generated maze result: `success=True`, `goal_found=True`, `steps_taken=28`, `shortest_path_length=14`, `map_coverage=0.88`, `blocked_edges_encountered=2`, `replans=7`.

## Visual Evidence Demo

```powershell
python main.py --env visual_sequence --image-dir assets/test_sequences/bedroom_sequence --max-frames 3 --visual-local-hybrid --visual-task "Is the laptop on the chair?" --validate
python -m validators.validate_visual_task_evidence outputs/visual_task_result.json outputs/run_audit.json
```

Key outputs:

- `outputs/world_model.json`
- `outputs/episode_log.jsonl`
- `outputs/run_audit.json`
- `outputs/visual_task_result.json`

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

## Report And Source Package

```powershell
python tools/generate_project_report.py
python tools/package_source.py
python tools/create_submission_bundle.py
python tools/pre_submission_audit.py
```

Expected output:

- `reports/v0.8.4_technical_report.md`
- `dist/eagc_track1_mvp_source.zip`
