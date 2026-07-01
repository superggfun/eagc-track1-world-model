# Docker Run Examples

Build the agent image:

```bash
docker build -t eagc-track1-agent:v0.17.6 .
```

Run mock-only Docker smoke checks:

```bash
docker run --rm eagc-track1-agent:v0.17.6 python tools/run_test_suite.py --tier docker-smoke
```

Run a LocalSim Track 1 procedure against a host vLLM service on Windows Docker Desktop:

```bash
docker run --rm ^
  -e QWEN_BASE_URL=http://host.docker.internal:8000/v1 ^
  -e QWEN_MODEL=qwen3.6-35b-nvfp4 ^
  eagc-track1-agent:v0.17.6 ^
  python -m harness.run_track1 --env local_sim --episode-id local-explore-book-relocated --output-dir /app/outputs/local_sim_track1_demo --validate
```

Run the same command on Linux with host networking:

```bash
docker run --rm --network host \
  -e QWEN_BASE_URL=http://127.0.0.1:8000/v1 \
  -e QWEN_MODEL=qwen3.6-35b-nvfp4 \
  eagc-track1-agent:v0.17.6 \
  python -m harness.run_track1 --env local_sim --episode-id local-explore-book-relocated --output-dir /app/outputs/local_sim_track1_demo --validate
```

Reproduce the sample LocalSim output with Windows PowerShell:

```powershell
docker run --rm -v "${PWD}/outputs:/app/outputs" eagc-track1-agent:v0.17.6 python -m harness.run_track1 --env local_sim --episode-id local-explore-book-relocated --output-dir /app/outputs/local_sim_track1_demo --validate --mock
```

Reproduce the sample visual evidence output with Windows PowerShell:

```powershell
docker run --rm -v "${PWD}/outputs:/app/outputs" -v "${PWD}/assets:/app/assets:ro" eagc-track1-agent:v0.17.6 python -m harness.run_visual_demo --frames /app/assets/test_sequences/bedroom_sequence --output-dir /app/outputs/visual_evidence_demo --validate --mock
```

Run MazeSim predicted/reference evidence and validation:

```bash
docker run --rm -v "${PWD}/outputs:/app/outputs" eagc-track1-agent:v0.17.6 python tools/run_maze_stress_test.py --output-dir /app/outputs/maze_stress
docker run --rm -v "${PWD}/outputs:/app/outputs" eagc-track1-agent:v0.17.6 python -m validators.validate_maze_outputs --output-dir /app/outputs/maze_stress --recursive
```

Run the official adapter placeholder. This is expected to fail closed until official runtime connection details are provided:

```bash
docker run --rm \
  -e EAGC_EPISODE_ID=hidden_episode \
  -e EAGC_OUTPUT_DIR=/app/outputs/official \
  -v "${PWD}/outputs:/app/outputs" \
  eagc-track1-agent:v0.17.6 \
  python -m harness.run_official --output-dir /app/outputs/official --validate
```

Validate VirtualHome replay mechanics in Docker smoke mode:

```bash
docker run --rm -v "${PWD}/outputs:/app/outputs" eagc-track1-agent:v0.17.6 python -m harness.run_virtualhome_replay --frames assets/test_sequences/virtualhome_exploration/frames --manifest assets/test_sequences/virtualhome_exploration/frame_manifest.json --output-dir /app/outputs/virtualhome_exploration_replay --prediction-input-mode mock_visual_extraction --validate
```
