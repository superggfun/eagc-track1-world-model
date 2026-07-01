from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def main() -> int:
    print(f"Python: {sys.version.split()[0]}")
    try:
        _check_imports()
        config = _load_config()
        _check_optional_vllm(config)
        _run_mock_smoke()
    except Exception as exc:
        print(f"Docker smoke check failed: {exc}")
        return 1
    print("Docker smoke check passed.")
    return 0


def _check_imports() -> None:
    import clients.qwen_client  # noqa: F401
    import executor.action_executor  # noqa: F401
    import logging_utils.episode_logger  # noqa: F401
    import main as main_module  # noqa: F401
    import perception.vlm_extractor  # noqa: F401
    import planner.replanner  # noqa: F401
    import planner.rule_planner  # noqa: F401
    import task_evaluator.task_evaluator  # noqa: F401
    import validators.validate_episode_log  # noqa: F401
    import validators.validate_semantic_consistency  # noqa: F401
    import validators.validate_world_model  # noqa: F401
    import world_model.store  # noqa: F401

    print("Import check: ok")


def _load_config() -> dict[str, Any]:
    from main import load_config

    config = load_config(PROJECT_ROOT / "config.yaml")
    print(
        "Config: "
        + json.dumps(
            {
                "base_url": config.get("base_url"),
                "model": config.get("model"),
                "temperature": config.get("temperature"),
                "max_tokens": config.get("max_tokens"),
            },
            ensure_ascii=False,
        )
    )
    return config


def _check_optional_vllm(config: dict[str, Any]) -> None:
    base_url = os.environ.get("QWEN_BASE_URL")
    if not base_url:
        print("QWEN_BASE_URL not set; skipping optional /models check.")
        return
    url = base_url.rstrip("/") + "/models"
    started = time.perf_counter()
    try:
        response = requests.get(url, timeout=5)
        latency = time.perf_counter() - started
        if response.status_code >= 400:
            print(f"WARNING: vLLM /models returned HTTP {response.status_code} from {url}")
        else:
            print(f"vLLM /models reachable at {url} in {latency:.2f}s")
    except requests.RequestException as exc:
        print(f"WARNING: could not reach vLLM /models at {url}: {exc}")
        print(f"Configured base_url remains {config.get('base_url')!r}; mock-only smoke can continue.")


def _run_mock_smoke() -> None:
    output_dir = PROJECT_ROOT / "outputs" / "docker_smoke" / "mock_nominal"
    command = [
        sys.executable,
        "main.py",
        "--episode-id",
        "mock-livingroom-nominal",
        "--use-mock-llm",
        "--validate",
        "--output-dir",
        str(output_dir),
    ]
    print(f"$ {' '.join(command)}")
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    if completed.returncode != 0:
        raise RuntimeError(f"mock smoke failed with exit code {completed.returncode}")


if __name__ == "__main__":
    raise SystemExit(main())
