# Docker Submission Readiness

This Docker image packages the EAGC Track 1 local MVP agent code: inference clients, world-model update modules, planners, replanners, task evaluators, validators, diagnostics, and demo/test commands.

The image does **not** include Qwen3.6-35B-A3B-NVFP4 model weights. Model inference is expected to run as an external OpenAI-compatible vLLM service.

## Build

```bash
docker build -t eagc-track1-agent:v0.17.6 .
```

## Mock-Only Smoke Test

This does not call the real Qwen endpoint and does not require local images, AI2-THOR, or ProcTHOR.

```bash
docker run --rm eagc-track1-agent:v0.17.6 python tools/run_test_suite.py --tier docker-smoke
```

## Configure External Qwen vLLM

The container reads these environment variables and uses them to override `config.yaml`:

- `QWEN_BASE_URL`
- `QWEN_MODEL`
- `QWEN_TEMPERATURE`
- `QWEN_MAX_TOKENS`

If they are not set, the defaults in `config.yaml` are used.

## Connect to Host vLLM

Windows Docker Desktop commonly exposes the host through `host.docker.internal`:

```bash
docker run --rm \
  -e QWEN_BASE_URL=http://host.docker.internal:8000/v1 \
  -e QWEN_MODEL=qwen3.6-35b-nvfp4 \
  eagc-track1-agent:v0.17.6 \
  python -m harness.run_track1 --env local_sim --episode-id local-explore-book-relocated --output-dir /app/outputs/local_sim_track1_demo --validate
```

On Linux, host networking is often the simplest option:

```bash
docker run --rm --network host \
  -e QWEN_BASE_URL=http://127.0.0.1:8000/v1 \
  -e QWEN_MODEL=qwen3.6-35b-nvfp4 \
  eagc-track1-agent:v0.17.6 \
  python -m harness.run_track1 --env local_sim --episode-id local-explore-book-relocated --output-dir /app/outputs/local_sim_track1_demo --validate
```

## Reproduce Sample Outputs

Windows PowerShell example with a mounted output directory:

```powershell
docker run --rm -v "${PWD}/outputs:/app/outputs" eagc-track1-agent:v0.17.6 python -m harness.run_track1 --env local_sim --episode-id local-explore-book-relocated --output-dir /app/outputs/local_sim_track1_demo --validate --mock
```

Visual evidence runs need local frame images mounted into the container:

```powershell
docker run --rm -v "${PWD}/outputs:/app/outputs" -v "${PWD}/assets:/app/assets:ro" eagc-track1-agent:v0.17.6 python -m harness.run_visual_demo --frames /app/assets/test_sequences/bedroom_sequence --output-dir /app/outputs/visual_evidence_demo --validate --mock
```

If the container cannot access vLLM, first run mock-only checks:

```bash
docker run --rm eagc-track1-agent:v0.17.6 python tools/run_test_suite.py --tier docker-smoke
```

Then verify the host endpoint outside the container and adjust Docker networking without changing the vLLM container.

## MazeSim Replay-Free Validation

MazeSim is synthetic and does not require Unity, external simulator assets, Qwen/vLLM, or network access. Docker can run the predicted/reference validation path directly:

```bash
docker run --rm -v "${PWD}/outputs:/app/outputs" eagc-track1-agent:v0.17.6 python tools/run_maze_stress_test.py --output-dir /app/outputs/maze_stress
docker run --rm -v "${PWD}/outputs:/app/outputs" eagc-track1-agent:v0.17.6 python -m validators.validate_maze_outputs --output-dir /app/outputs/maze_stress --recursive
```

The predicted `world_model.json` is generated from exploration observations and action results. `reference_maze.json` is a validation-only answer key, and `comparison_report.json` records local precision/recall. These outputs are not official hidden-evaluation scores.

## Official Runtime Placeholder

The image includes a fail-closed official adapter boundary. This command is ready for future official runtime configuration, but it will exit non-zero until the official SDK/RPC/socket/HTTP details are released and wired in `src/env_adapters/official_env.py`.

```bash
docker run --rm \
  -e EAGC_EPISODE_ID=hidden_episode \
  -e EAGC_OUTPUT_DIR=/app/outputs/official \
  -v "$(pwd)/outputs:/app/outputs" \
  eagc-track1-agent:v0.17.6 \
  python -m harness.run_official --output-dir /app/outputs/official --validate
```

Official mode never falls back to LocalSim and does not create fake official outputs.

## VirtualHome Replay Evidence

Docker is not expected to launch the full Windows VirtualHome/Unity runtime. Final live evidence is generated on the Windows host:

```powershell
python -m harness.run_virtualhome_live ^
  --virtualhome-exe "<YOUR_VIRTUALHOME_WINDOWS_EXEC_PATH>" ^
  --output-dir outputs/virtualhome_exploration ^
  --prediction-input-mode vlm_frame_extraction ^
  --continuous-run ^
  --validate
```

Replay validation for final evidence uses VLM mode when a local vision endpoint is available:

```powershell
python -m harness.run_virtualhome_replay ^
  --frames assets/test_sequences/virtualhome_exploration/frames ^
  --manifest assets/test_sequences/virtualhome_exploration/frame_manifest.json ^
  --output-dir outputs/virtualhome_exploration_replay ^
  --prediction-input-mode vlm_frame_extraction ^
  --validate
```

Container smoke can validate replay mechanics without Unity or VLM access:

```bash
docker run --rm -v "${PWD}/outputs:/app/outputs" eagc-track1-agent:v0.17.6 python -m harness.run_virtualhome_replay --frames assets/test_sequences/virtualhome_exploration/frames --manifest assets/test_sequences/virtualhome_exploration/frame_manifest.json --output-dir /app/outputs/virtualhome_exploration_replay --prediction-input-mode mock_visual_extraction --validate
```

`mock_visual_extraction` is for CI/smoke only. The submitted `submission_bundle/sample_outputs/virtualhome_exploration/` must come from `vlm_frame_extraction`. The VirtualHome scene graph is reference-only and these outputs are not official hidden-evaluation scores.

