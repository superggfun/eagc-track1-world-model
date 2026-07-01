from __future__ import annotations

import json
import socket
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "resource_profile"
JSON_PATH = OUTPUT_DIR / "virtualhome_vllm_resource_profile.json"
MD_PATH = OUTPUT_DIR / "virtualhome_vllm_resource_profile.md"
DEFAULT_QWEN_BASE_URL = "http://127.0.0.1:8000/v1"
VLLM_CONTAINER_NAME = "openclaw-vllm"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    profile = build_profile()
    JSON_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_PATH.write_text(_markdown(profile), encoding="utf-8")
    print(f"Resource profile written to {JSON_PATH}")
    print(f"Resource profile written to {MD_PATH}")
    return 0


def build_profile(base_url: str = DEFAULT_QWEN_BASE_URL) -> Dict[str, Any]:
    docker = _docker_status()
    profile: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gpu": _gpu_status(),
        "docker": docker,
        "openclaw_vllm": _openclaw_vllm_status(docker),
        "virtualhome": {
            "host": "127.0.0.1",
            "port": 8080,
            "listening": _is_port_open("127.0.0.1", 8080),
        },
        "qwen_endpoint": _qwen_models_status(base_url),
        "notes": [
            "This tool only reads process/container/resource state.",
            "It does not start, stop, restart, delete, rebuild, or modify Docker containers.",
            "It does not start lightweight vLLM.",
        ],
    }
    return profile


def _gpu_status() -> Dict[str, Any]:
    query = _run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
    )
    processes = _run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    raw = _run(["nvidia-smi"])
    devices = []
    for line in query["stdout"].splitlines():
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

    process_rows = []
    for line in processes["stdout"].splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        process_rows.append(
            {
                "pid": _to_int(parts[0]),
                "process_name": parts[1],
                "used_memory_mib": _to_int(parts[2]),
            }
        )
    return {
        "nvidia_smi_available": query["returncode"] == 0 or raw["returncode"] == 0,
        "devices": devices,
        "compute_processes": process_rows,
        "raw_nvidia_smi": raw["stdout"] or raw["stderr"],
        "errors": [item for item in [query["stderr"], processes["stderr"], raw["stderr"]] if item],
    }


def _docker_status() -> Dict[str, Any]:
    version = _run(["docker", "--version"])
    ps = _run(["docker", "ps", "--format", "{{json .}}"])
    containers = []
    if ps["returncode"] == 0:
        for line in ps["stdout"].splitlines():
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                containers.append({"raw": line})
    return {
        "docker_available": version["returncode"] == 0,
        "version_stdout": version["stdout"].strip(),
        "version_stderr": version["stderr"].strip(),
        "ps_returncode": ps["returncode"],
        "containers": containers,
        "error": ps["stderr"].strip() if ps["returncode"] != 0 else "",
    }


def _openclaw_vllm_status(docker: Dict[str, Any]) -> Dict[str, Any]:
    matches = []
    for container in docker.get("containers", []):
        if not isinstance(container, dict):
            continue
        haystack = " ".join(
            str(container.get(key, ""))
            for key in ["Names", "Image", "Ports", "Command", "ID", "State", "Status"]
        ).lower()
        if VLLM_CONTAINER_NAME in haystack or "vllm" in haystack:
            matches.append(container)
    return {
        "expected_name": VLLM_CONTAINER_NAME,
        "running": bool(matches),
        "matches": matches,
        "note": "Container status is read-only. This script never manages Docker containers.",
    }


def _qwen_models_status(base_url: str) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/models"
    status: Dict[str, Any] = {
        "base_url": base_url,
        "models_url": url,
        "available": False,
        "model_ids": [],
        "error_type": "",
        "error_message": "",
    }
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        status["model_ids"] = [item.get("id") for item in payload.get("data", []) if isinstance(item, dict)]
        status["available"] = True
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        status["error_type"] = type(exc).__name__
        status["error_message"] = str(exc)
    return status


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def _run(command: List[str]) -> Dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
        }
    except FileNotFoundError as exc:
        return {"command": command, "returncode": 127, "stdout": "", "stderr": str(exc)}


def _to_int(value: str) -> int | None:
    try:
        return int(float(value.strip()))
    except (TypeError, ValueError):
        return None


def _markdown(profile: Dict[str, Any]) -> str:
    gpu = profile.get("gpu", {})
    qwen = profile.get("qwen_endpoint", {})
    virtualhome = profile.get("virtualhome", {})
    openclaw = profile.get("openclaw_vllm", {})
    lines = [
        "# VirtualHome + vLLM Resource Profile",
        "",
        f"- timestamp: `{profile.get('timestamp')}`",
        f"- VirtualHome 127.0.0.1:8080 listening: `{virtualhome.get('listening')}`",
        f"- Qwen endpoint available: `{qwen.get('available')}`",
        f"- Qwen models: `{', '.join(qwen.get('model_ids', []))}`",
        f"- openclaw/vLLM container running: `{openclaw.get('running')}`",
        "",
        "## GPU Devices",
        "",
        "| index | name | total MiB | used MiB | free MiB | util % |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for device in gpu.get("devices", []):
        lines.append(
            f"| {device.get('index')} | {device.get('name')} | {device.get('memory_total_mib')} | "
            f"{device.get('memory_used_mib')} | {device.get('memory_free_mib')} | "
            f"{device.get('utilization_gpu_percent')} |"
        )
    lines.extend(["", "## GPU Compute Processes", "", "| pid | process | used MiB |", "|---:|---|---:|"])
    for process in gpu.get("compute_processes", []):
        lines.append(f"| {process.get('pid')} | {process.get('process_name')} | {process.get('used_memory_mib')} |")
    if not gpu.get("compute_processes"):
        lines.append("| none | none | 0 |")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This is a read-only audit.",
            "- It does not start lightweight vLLM.",
            "- It does not manage the original Qwen/vLLM Docker container.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
