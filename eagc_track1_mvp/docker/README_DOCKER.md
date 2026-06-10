# Docker Submission Readiness

This Docker image packages the EAGC Track 1 local MVP agent code: inference clients, world-model update modules, planners, replanners, task evaluators, validators, diagnostics, and demo/test commands.

The image does **not** include Qwen3.6-35B-A3B-NVFP4 model weights. Model inference is expected to run as an external OpenAI-compatible vLLM service.

## Build

```bash
docker build -t eagc-track1-agent:v0.11 .
```

## Mock-Only Smoke Test

This does not call the real Qwen endpoint and does not require local images, AI2-THOR, or ProcTHOR.

```bash
docker run --rm eagc-track1-agent:v0.11 python tools/run_test_suite.py --tier docker-smoke
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
  eagc-track1-agent:v0.11 \
  python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
```

On Linux, host networking is often the simplest option:

```bash
docker run --rm --network host \
  -e QWEN_BASE_URL=http://127.0.0.1:8000/v1 \
  -e QWEN_MODEL=qwen3.6-35b-nvfp4 \
  eagc-track1-agent:v0.11 \
  python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
```

If the container cannot access vLLM, first run mock-only checks:

```bash
docker run --rm eagc-track1-agent:v0.11 python tools/run_test_suite.py --tier docker-smoke
```

Then verify the host endpoint outside the container and adjust Docker networking without changing the vLLM container.
