from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.check_vllm_endpoint import check_endpoint


OUTPUT_PATH = Path("outputs/virtualhome_spike/coexistence_status.json")


def _run(command: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _gpu_snapshot() -> Dict[str, Any]:
    query = _run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
    )
    return {
        "returncode": query.returncode,
        "stdout": query.stdout.strip(),
        "stderr": query.stderr.strip(),
    }


def _post_json(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def run_check(base_url: str, model: str, timeout: float, virtualhome_status_path: Path) -> Dict[str, Any]:
    started = time.perf_counter()
    status: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": False,
        "base_url": base_url,
        "model": model,
        "virtualhome_status_path": str(virtualhome_status_path),
        "virtualhome_ok": False,
        "vllm_models_ok": False,
        "vllm_chat_ok": False,
        "failure_stage": "",
        "error_type": "",
        "error_message": "",
        "gpu_before": _gpu_snapshot(),
        "gpu_after": None,
        "latency_seconds": None,
    }

    try:
        virtualhome_status = _read_json(virtualhome_status_path)
        status["virtualhome_status"] = virtualhome_status
        status["virtualhome_ok"] = virtualhome_status.get("success") is True
        if not status["virtualhome_ok"]:
            status["failure_stage"] = "virtualhome_not_ready"
            status["error_message"] = f"VirtualHome status is not successful: {virtualhome_status.get('reason')}"
            return status

        endpoint_status = check_endpoint(base_url, timeout)
        status["vllm_endpoint_status"] = endpoint_status
        status["vllm_models_ok"] = endpoint_status.get("success") is True
        if not status["vllm_models_ok"]:
            status["failure_stage"] = "vllm_models_endpoint_failed"
            status["error_message"] = endpoint_status.get("error_message", "")
            return status

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": "Return JSON: {\"ok\": true}"},
            ],
            "temperature": 0,
            "max_tokens": 32,
        }
        completion = _post_json(f"{base_url.rstrip('/')}/chat/completions", payload, timeout)
        content = completion.get("choices", [{}])[0].get("message", {}).get("content", "")
        status["response_preview"] = str(content)[:200]
        status["vllm_chat_ok"] = bool(content)
        status["success"] = status["virtualhome_ok"] and status["vllm_models_ok"] and status["vllm_chat_ok"]
        if not status["success"]:
            status["failure_stage"] = "vllm_chat_completion_empty"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        status["failure_stage"] = "vllm_chat_request_failed"
        status["error_type"] = type(exc).__name__
        status["error_message"] = str(exc)
    finally:
        status["gpu_after"] = _gpu_snapshot()
        status["latency_seconds"] = round(time.perf_counter() - started, 3)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="Check VirtualHome + short vLLM request coexistence.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", default="qwen3.6-35b-nvfp4")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--virtualhome-status", default="outputs/virtualhome_spike/status.json")
    args = parser.parse_args()

    status = run_check(args.base_url, args.model, args.timeout, Path(args.virtualhome_status))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"VirtualHome/vLLM coexistence status written to {OUTPUT_PATH}")
    if not status["success"]:
        print(f"Coexistence check failed at {status['failure_stage']}: {status.get('error_message', '')}")
        return 1
    print("VirtualHome/vLLM coexistence check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
