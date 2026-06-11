from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


DEFAULT_BASE_URL = "http://127.0.0.1:8001/v1"
DEFAULT_MODEL = "qwen3.6-35b-nvfp4"
OUTPUT_PATH = Path("outputs/vllm_lite_test/status.json")


def _get_json(url: str, timeout: float) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def run_check(base_url: str, model: str, timeout: float) -> Dict[str, Any]:
    started = time.perf_counter()
    status: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "model": model,
        "success": False,
        "models_endpoint_ok": False,
        "model_found": False,
        "chat_completion_ok": False,
        "latency_seconds": None,
        "error_type": "",
        "error_message": "",
    }
    try:
        models = _get_json(f"{base_url.rstrip('/')}/models", timeout)
        status["models_endpoint_ok"] = True
        ids = [item.get("id") for item in models.get("data", []) if isinstance(item, dict)]
        status["available_models"] = ids
        status["model_found"] = model in ids

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return a short JSON object only."},
                {"role": "user", "content": "Reply with {\"ok\": true}."},
            ],
            "temperature": 0,
            "max_tokens": 64,
        }
        completion = _post_json(f"{base_url.rstrip('/')}/chat/completions", payload, timeout)
        content = (
            completion.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        status["chat_completion_ok"] = bool(content)
        status["response_preview"] = str(content)[:200]
        status["success"] = status["models_endpoint_ok"] and status["model_found"] and status["chat_completion_ok"]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        status["error_type"] = type(exc).__name__
        status["error_message"] = str(exc)
    finally:
        status["latency_seconds"] = round(time.perf_counter() - started, 3)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="Test the lightweight vLLM endpoint for VirtualHome sharing.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    status = run_check(args.base_url, args.model, args.timeout)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"vLLM lite endpoint status written to {OUTPUT_PATH}")
    if not status["success"]:
        print(f"vLLM lite endpoint check failed: {status.get('error_message') or status}")
        return 1
    print("vLLM lite endpoint check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
