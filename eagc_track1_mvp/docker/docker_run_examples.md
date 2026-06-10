# Docker Run Examples

Build the agent image:

```bash
docker build -t eagc-track1-agent:v0.11 .
```

Run mock-only Docker smoke checks:

```bash
docker run --rm eagc-track1-agent:v0.11 python tools/run_test_suite.py --tier docker-smoke
```

Run a LocalSim Track 1 procedure against a host vLLM service on Windows Docker Desktop:

```bash
docker run --rm ^
  -e QWEN_BASE_URL=http://host.docker.internal:8000/v1 ^
  -e QWEN_MODEL=qwen3.6-35b-nvfp4 ^
  eagc-track1-agent:v0.11 ^
  python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
```

Run the same command on Linux with host networking:

```bash
docker run --rm --network host \
  -e QWEN_BASE_URL=http://127.0.0.1:8000/v1 \
  -e QWEN_MODEL=qwen3.6-35b-nvfp4 \
  eagc-track1-agent:v0.11 \
  python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
```
