# Reproducibility Statement

## Environment Assumptions

- Operating system: Windows local development environment.
- Python: 3.10+ recommended.
- Local vLLM server: already running before tests.
- vLLM endpoint: `http://127.0.0.1:8000/v1`.
- Model identifier: `qwen3.6-35b-nvfp4`.
- The project does not start, stop, restart, or manage the vLLM Docker container.

## Installation

```powershell
cd <repo-root>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Test Commands

Fast tier:

```powershell
python tools/run_test_suite.py --tier fast
```

Fast is deterministic and does not call real Qwen, real vision, external simulators, local images, or real ALFRED data.

List tiers:

```powershell
python tools/run_test_suite.py --list-tiers
```

List environment adapter capabilities without starting simulators:

```powershell
python tools/list_env_adapters.py
```

This writes `outputs/adapter_capabilities/adapter_capabilities.json` and `.md`. LocalSim and VirtualHome are marked as validated backends. MazeSim is marked as a validated synthetic topology stress backend. ALFRED offline is marked as synthetic-fixture validated. AI2-THOR, Habitat, and ProcTHOR are reserved but not validated.

Targeted text:

```powershell
python tools/run_test_suite.py --tier targeted-text --timeout-seconds 300
```

Targeted LocalSim:

```powershell
python tools/run_test_suite.py --tier targeted-local-sim --timeout-seconds 600
```

Targeted MazeSim topology stress:

```powershell
python tools/run_test_suite.py --tier targeted-maze --timeout-seconds 300
python tools/run_maze_stress_test.py --output-dir outputs/maze_stress
python -m validators.validate_maze_outputs --output-dir outputs/maze_stress --recursive
```

MazeSim is deterministic and synthetic. Its predicted `world_model.json` is generated from observations, successful and failed navigation actions, frontier updates, and replanning traces. `reference_maze.json` is generated separately from the MazeSim spec as a local answer key for `comparison_report.json` and validation only; `reference_used_for_generation=false` is enforced. It does not call Qwen/vLLM, does not use external simulator assets, and is not an official EAGC runtime. The latest medium generated maze result was `success=True`, `goal_found=True`, `steps_taken=28`, `shortest_path_length=14`, `map_coverage=0.88`, `blocked_edges_encountered=2`, and `replans=7`.

Targeted MazeSim anti-loop and dead-end recovery stress:

```powershell
python tools/run_test_suite.py --tier targeted-maze-anti-loop --timeout-seconds 300
python tools/run_maze_anti_loop_test.py --output-dir outputs/maze_anti_loop
python -m validators.validate_maze_outputs --output-dir outputs/maze_anti_loop --recursive
```

This is also deterministic and synthetic. It does not call Qwen/vLLM, does not use external simulator assets, and is not an official EAGC runtime. Latest validated results: `loop_lure_maze` succeeded in 8 steps; `dead_end_comb_maze` succeeded in 26 steps with `repeated_state_count=10` and `replans=10`; `blocked_shortcut_maze` succeeded in 11 steps with `blocked_edges_encountered=1` and `replans=2`; `unreachable_goal_maze` terminated as an expected graceful failure with `goal_unreachable_or_budget_exhausted` in 3 steps.

The dead-end comb case intentionally lengthens the agent path through repeated dead-end discovery and backtracking; zero oscillation and eventual goal reach are the intended anti-loop signal. The blocked shortcut case prioritizes safe recovery over exhaustive map completion, so high precision and high-but-not-perfect recall are acceptable. The unreachable case records `expected_goal_reachable=false`, `goal_reached=false`, and `expected_outcome_met=true`.

VirtualHome manual-play evidence tiers, optional:

```powershell
python tools/run_test_suite.py --tier targeted-virtualhome-manual --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-virtualhome-frame --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-virtualhome-vision --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-virtualhome-multiframe --timeout-seconds 600
python tools/build_virtualhome_evidence_report.py
```

These require external VirtualHome resources, a manually running `VirtualHome.exe` in Play mode, and the existing local Qwen/vLLM endpoint for the vision tiers. They do not start lightweight vLLM and do not modify the existing Qwen Docker container.

VirtualHome + vLLM resource profile, optional:

```powershell
python tools/run_test_suite.py --tier targeted-resource-profile --timeout-seconds 300
```

This is a read-only resource audit. It records GPU memory, Docker/container summaries, VirtualHome port status, Qwen `/models` availability, and minimal text/frame-vision latency if both services are available. It does not start lightweight vLLM and does not stop, restart, rebuild, delete, or reconfigure the original Qwen/vLLM Docker container.

Aggregate targeted tier:

```powershell
python tools/run_test_suite.py --tier targeted --timeout-seconds 900 --continue-on-failure
```

The aggregate targeted tier can take several minutes and records per-command runtime reports under `outputs/test_suite_reports/`.

Standard tier:

```powershell
python tools/run_test_suite.py --tier standard
```

Full tier is available but not required for this readiness package:

```powershell
python tools/run_test_suite.py --tier full
```

Docker smoke tier:

```powershell
python tools/run_test_suite.py --tier docker-smoke
```

## Demo Snapshot Reproduction

```powershell
python tools/create_demo_snapshot.py
```

Expected output:

- `outputs/demo_snapshot/local_sim_track1_demo/`
- `outputs/demo_snapshot/visual_evidence_demo/`
- `outputs/demo_snapshot/README_demo.md`

## Report Generation

```powershell
python tools/generate_project_report.py
```

Expected output:

- `reports/v0.8.4_technical_report.md`

Note: this is the current report generator output path and uses a legacy filename from the first technical-report milestone. The current submission-facing technical report draft is `submission_package/technical_report_draft.md`, and `tools/build_report_pdf.py` writes HTML/PDF-status artifacts under `submission_bundle/reports/`.

## Source Package Generation

```powershell
python tools/package_source.py
```

Expected output:

- `dist/source.zip`

The package is generated from git tracked source files plus the harness refresh files when they are still untracked locally, and excludes outputs, local images, `.venv-ai2thor`, `source_pack`, zip files, and `__pycache__`.

Clean source package check:

```powershell
python tools/check_source_package_repro.py --zip-path dist/source.zip
```

Pre-submission audit:

```powershell
python tools/pre_submission_audit.py
```

## Docker Reproducibility

The Docker image packages only the local agent code. It does not include Qwen3.6-35B-A3B-NVFP4 model weights.

Build:

```powershell
docker build -t eagc-track1-agent:v0.17.6 .
```

Mock-only Docker smoke:

```powershell
docker run --rm eagc-track1-agent:v0.17.6 python tools/run_test_suite.py --tier docker-smoke
```

Windows Docker Desktop host vLLM example:

```powershell
docker run --rm -v "${PWD}/outputs:/app/outputs" -e QWEN_BASE_URL=http://host.docker.internal:8000/v1 -e QWEN_MODEL=qwen3.6-35b-nvfp4 eagc-track1-agent:v0.17.6 python -m harness.run_track1 --env local_sim --episode-id local-explore-book-relocated --output-dir /app/outputs/local_sim_track1_demo --validate
```

Linux host-network example:

```bash
docker run --rm --network host -v "$PWD/outputs:/app/outputs" -e QWEN_BASE_URL=http://127.0.0.1:8000/v1 -e QWEN_MODEL=qwen3.6-35b-nvfp4 eagc-track1-agent:v0.17.6 python -m harness.run_track1 --env local_sim --episode-id local-explore-book-relocated --output-dir /app/outputs/local_sim_track1_demo --validate
```

## Optional VirtualHome Multi-Room Evidence

Strict final live evidence:

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

Replay validation:

```powershell
python -m harness.run_virtualhome_replay ^
  --frames assets/test_sequences/virtualhome_exploration/frames ^
  --manifest assets/test_sequences/virtualhome_exploration/frame_manifest.json ^
  --output-dir outputs/virtualhome_exploration_replay ^
  --prediction-input-mode vlm_frame_extraction ^
  --validate
```

The predicted VirtualHome world model is generated from frame observations and action/navigation traces. The VirtualHome scene graph is used only as `reference_world_model.json` for local comparison, not prediction generation. `mock_visual_extraction` remains available for CI/smoke only and is never final sample evidence.

## Visual Test Images

Visual sequence and visual-local hybrid smoke tests require local images named like:

```text
assets/test_sequences/bedroom_sequence/frame_000.jpg
assets/test_sequences/bedroom_sequence/frame_001.jpg
assets/test_sequences/bedroom_sequence/frame_002.jpg
```

These images are local resources and are intentionally not committed.
