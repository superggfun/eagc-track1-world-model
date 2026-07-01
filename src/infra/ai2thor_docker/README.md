# AI2-THOR Docker Rendering Smoke

This directory is an isolated AI2-THOR / Unity rendering experiment. It is intentionally separate from the main `eagc-track1-agent` Docker image and is not part of the stable EAGC agent test tiers.

Goals:

- Install AI2-THOR and basic X/GL runtime dependencies.
- Include Vulkan runtime dependencies needed by AI2-THOR `CloudRendering`.
- Run `tools/check_ai2thor_rendering_env.py`.
- Run `tools/run_ai2thor_minimal_render_test.py` with a timeout.
- Diagnose whether Docker GPU / X / CloudRendering is viable on this host.

This route does not include Qwen model weights and does not call the local Qwen vLLM service.

## Build

```bash
docker build -f infra/ai2thor_docker/Dockerfile.ai2thor-smoke -t ai2thor-render-smoke:latest .
```

## Run CloudRendering

```bash
docker run --rm --gpus all -e NVIDIA_DRIVER_CAPABILITIES=all -v "$PWD/outputs:/app/outputs" ai2thor-render-smoke:latest \
  python tools/run_ai2thor_minimal_render_test.py --platform cloud --timeout-seconds 180
```

## Run Default Rendering With Xvfb

```bash
docker run --rm --gpus all -e NVIDIA_DRIVER_CAPABILITIES=all -v "$PWD/outputs:/app/outputs" ai2thor-render-smoke:latest \
  xvfb-run -s "-screen 0 1024x768x24" python tools/run_ai2thor_minimal_render_test.py --platform default --timeout-seconds 180
```

## Notes

- Docker GPU support requires NVIDIA Container Toolkit.
- `NVIDIA_DRIVER_CAPABILITIES=all` is recommended so graphics/Vulkan capabilities are exposed in addition to compute.
- Local Windows Docker Desktop GPU behavior may differ from native Linux.
- This image is for diagnostics only and should not replace the main submission Docker image.
