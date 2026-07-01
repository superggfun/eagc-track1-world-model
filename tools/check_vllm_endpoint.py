from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


OUTPUT_PATH = Path("outputs/local_runtime_check/vllm_endpoint_status.json")


def _get_json(url: str, timeout: float) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_endpoint(base_url: str, timeout: float) -> Dict[str, Any]:
    started = time.perf_counter()
    status: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "success": False,
        "models_endpoint_ok": False,
        "model_ids": [],
        "latency_seconds": None,
        "error_type": "",
        "error_message": "",
    }
    try:
        data = _get_json(f"{base_url.rstrip('/')}/models", timeout)
        ids = [item.get("id") for item in data.get("data", []) if isinstance(item, dict)]
        status["models_endpoint_ok"] = True
        status["model_ids"] = ids
        status["success"] = True
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        status["error_type"] = type(exc).__name__
        status["error_message"] = str(exc)
    finally:
        status["latency_seconds"] = round(time.perf_counter() - started, 3)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a vLLM/OpenAI-compatible /models endpoint only.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    status = check_endpoint(args.base_url, args.timeout)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"vLLM endpoint status written to {OUTPUT_PATH}")
    if status["success"]:
        print("Models:")
        for model_id in status["model_ids"]:
            print(f"- {model_id}")
        return 0
    print(f"vLLM endpoint check failed: {status['error_type']} {status['error_message']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
