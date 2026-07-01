from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clients.qwen_client import QwenClient, QwenClientError  # noqa: E402
from main import load_config  # noqa: E402
from perception.json_utils import extract_json_from_text, parse_json_from_text  # noqa: E402


OUTPUT_DIR = PROJECT_ROOT / "outputs" / "resource_profile"
STATUS_PATH = OUTPUT_DIR / "coexistence_smoke_status.json"
VIRTUALHOME_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "virtualhome_spike"
FRAME_PATH = VIRTUALHOME_OUTPUT_DIR / "frame_000.png"


VISION_PROMPT = """Inspect this VirtualHome simulator frame.
Return one compact JSON object only, no markdown:
{
  "visible_objects": ["object_name"],
  "short_description": "one sentence"
}
Use only visible evidence."""


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    status = run_smoke()
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VirtualHome/vLLM coexistence smoke status written to {STATUS_PATH}")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def run_smoke() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": False,
        "reason": "",
        "virtualhome_listening": _is_port_open("127.0.0.1", 8080),
        "qwen_endpoint_available": False,
        "frame_path": str(FRAME_PATH),
        "frame_ready": False,
        "gpu_before": _gpu_snapshot(),
        "gpu_after": {},
        "text_smoke": {},
        "vision_smoke": {},
        "notes": [
            "This script does not start or stop Docker containers.",
            "This script does not start lightweight vLLM.",
            "This script uses only the existing Qwen endpoint and current VirtualHome manual-play process if available.",
        ],
    }

    if not status["virtualhome_listening"]:
        status["reason"] = "virtualhome_not_listening"
        status["gpu_after"] = _gpu_snapshot()
        return status

    frame_status = _ensure_frame()
    status["frame_export"] = frame_status
    status["frame_ready"] = FRAME_PATH.exists() and FRAME_PATH.stat().st_size > 0

    config = load_config(PROJECT_ROOT / "config.yaml")
    client = QwenClient(
        base_url=str(config["base_url"]),
        model=str(config["model"]),
        temperature=0.0,
        max_tokens=128,
        timeout_seconds=90,
        audit_path=OUTPUT_DIR / "coexistence_qwen_calls.jsonl",
    )

    text_result = _run_text_smoke(client)
    status["text_smoke"] = text_result
    status["qwen_endpoint_available"] = text_result.get("success") is True
    if not text_result.get("success"):
        status["reason"] = "qwen_endpoint_unavailable"
        status["gpu_after"] = _gpu_snapshot()
        return status

    if status["frame_ready"]:
        status["vision_smoke"] = _run_vision_smoke(client)
    else:
        status["vision_smoke"] = {
            "success": False,
            "reason": "virtualhome_frame_unavailable",
            "latency_seconds": 0.0,
            "error_type": "",
            "error_message": "VirtualHome frame was not available for vision smoke.",
        }

    status["gpu_after"] = _gpu_snapshot()
    status["success"] = bool(text_result.get("success") and status["vision_smoke"].get("success"))
    status["reason"] = "virtualhome_vllm_coexistence_smoke_completed" if status["success"] else "virtualhome_vllm_coexistence_smoke_incomplete"
    return status


def _ensure_frame() -> Dict[str, Any]:
    if FRAME_PATH.exists() and FRAME_PATH.stat().st_size > 0:
        return {"success": True, "reason": "existing_frame_reused", "frame_path": str(FRAME_PATH)}
    command = [sys.executable, "tools/test_virtualhome_windows_spike.py", "--export-frame"]
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False, timeout=120)
    return {
        "success": completed.returncode == 0 and FRAME_PATH.exists() and FRAME_PATH.stat().st_size > 0,
        "reason": "frame_export_attempted",
        "command": " ".join(command),
        "returncode": completed.returncode,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "stdout_tail": completed.stdout[-1200:],
        "stderr_tail": completed.stderr[-1200:],
        "frame_path": str(FRAME_PATH),
    }


def _run_text_smoke(client: QwenClient) -> Dict[str, Any]:
    started = time.perf_counter()
    result: Dict[str, Any] = {
        "success": False,
        "reason": "",
        "latency_seconds": 0.0,
        "error_type": "",
        "error_message": "",
        "response_preview": "",
    }
    messages = [
        {"role": "system", "content": "Return compact JSON only. No markdown."},
        {"role": "user", "content": "Return exactly this JSON object: {\"ok\": true}"},
    ]
    try:
        raw = client.chat_text(messages, temperature=0.0, max_tokens=64)
        result["response_preview"] = raw[:300]
        parsed = json.loads(extract_json_from_text(raw))
        result["success"] = parsed.get("ok") is True
        result["reason"] = "qwen_text_smoke_completed" if result["success"] else "qwen_text_parse_failed"
    except (QwenClientError, ValueError, json.JSONDecodeError) as exc:
        result["reason"] = "qwen_text_smoke_failed"
        result["error_type"] = type(exc).__name__
        result["error_message"] = str(exc)
    finally:
        result["latency_seconds"] = round(time.perf_counter() - started, 3)
    return result


def _run_vision_smoke(client: QwenClient) -> Dict[str, Any]:
    started = time.perf_counter()
    result: Dict[str, Any] = {
        "success": False,
        "reason": "",
        "latency_seconds": 0.0,
        "error_type": "",
        "error_message": "",
        "visible_object_count": 0,
        "response_preview": "",
    }
    try:
        raw = client.chat_vision(FRAME_PATH, VISION_PROMPT, temperature=0.1, max_tokens=256)
        result["response_preview"] = raw[:500]
        parsed = parse_json_from_text(raw)
        visible = parsed.get("visible_objects", []) if isinstance(parsed, dict) else []
        if not isinstance(visible, list):
            visible = []
        result["visible_object_count"] = len(visible)
        result["success"] = True
        result["reason"] = "qwen_vision_smoke_completed"
    except (QwenClientError, ValueError, TypeError) as exc:
        result["reason"] = "qwen_vision_smoke_failed"
        result["error_type"] = type(exc).__name__
        result["error_message"] = str(exc)
    finally:
        result["latency_seconds"] = round(time.perf_counter() - started, 3)
    return result


def _gpu_snapshot() -> Dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        return {"available": False, "error": str(exc), "devices": []}
    devices = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 6:
            continue
        devices.append(
            {
                "index": _to_int(parts[0]),
                "name": parts[1],
                "memory_total_mib": _to_int(parts[2]),
                "memory_used_mib": _to_int(parts[3]),
                "memory_free_mib": _to_int(parts[4]),
                "utilization_gpu_percent": _to_int(parts[5]),
            }
        )
    return {
        "available": completed.returncode == 0,
        "devices": devices,
        "stderr": completed.stderr.strip(),
    }


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def _to_int(value: str) -> int | None:
    try:
        return int(float(value.strip()))
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
