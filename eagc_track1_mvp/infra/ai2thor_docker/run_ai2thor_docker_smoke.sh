#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-ai2thor-render-smoke:latest}"
PLATFORM="${PLATFORM:-cloud}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-180}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

docker build -f "${REPO_ROOT}/infra/ai2thor_docker/Dockerfile.ai2thor-smoke" -t "${IMAGE_NAME}" "${REPO_ROOT}"

docker run --rm --gpus all \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -v "${REPO_ROOT}/outputs:/app/outputs" \
  "${IMAGE_NAME}" \
  python3 tools/check_ai2thor_rendering_env.py

if [[ "${PLATFORM}" == "default" ]]; then
  docker run --rm --gpus all \
    -e NVIDIA_DRIVER_CAPABILITIES=all \
    -v "${REPO_ROOT}/outputs:/app/outputs" \
    "${IMAGE_NAME}" \
    xvfb-run -s "-screen 0 1024x768x24" python3 tools/run_ai2thor_minimal_render_test.py --platform default --timeout-seconds "${TIMEOUT_SECONDS}"
else
  docker run --rm --gpus all \
    -e NVIDIA_DRIVER_CAPABILITIES=all \
    -v "${REPO_ROOT}/outputs:/app/outputs" \
    "${IMAGE_NAME}" \
    python3 tools/run_ai2thor_minimal_render_test.py --platform cloud --timeout-seconds "${TIMEOUT_SECONDS}"
fi
