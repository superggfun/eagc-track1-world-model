from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


OUTPUT_PATH = Path("outputs/gpu_budget/gpu_status.json")


def _run(command: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _parse_csv_rows(text: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append([part.strip() for part in line.split(",")])
    return rows


def collect_gpu_status() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nvidia_smi_available": False,
        "gpus": [],
        "processes": [],
        "errors": [],
    }

    gpu_query = _run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
    )
    if gpu_query.returncode != 0:
        status["errors"].append((gpu_query.stderr or gpu_query.stdout or "nvidia-smi failed").strip())
        return status

    status["nvidia_smi_available"] = True
    for row in _parse_csv_rows(gpu_query.stdout):
        if len(row) < 6:
            continue
        status["gpus"].append(
            {
                "index": int(row[0]),
                "name": row[1],
                "memory_total_mb": int(row[2]),
                "memory_used_mb": int(row[3]),
                "memory_free_mb": int(row[4]),
                "utilization_gpu_percent": int(row[5]),
            }
        )

    process_query = _run(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    if process_query.returncode == 0:
        for row in _parse_csv_rows(process_query.stdout):
            if len(row) < 4:
                continue
            status["processes"].append(
                {
                    "gpu_uuid": row[0],
                    "pid": row[1],
                    "process_name": row[2],
                    "used_memory_mb": _safe_int(row[3]),
                }
            )
    elif process_query.stderr:
        status["errors"].append(process_query.stderr.strip())

    return status


def _safe_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def main() -> int:
    status = collect_gpu_status()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")

    print(f"GPU status written to {OUTPUT_PATH}")
    if not status["nvidia_smi_available"]:
        print("nvidia-smi is not available or failed.")
        return 1

    for gpu in status["gpus"]:
        print(
            "GPU {index}: {name} total={memory_total_mb}MB used={memory_used_mb}MB "
            "free={memory_free_mb}MB util={utilization_gpu_percent}%".format(**gpu)
        )
    if status["processes"]:
        print("GPU processes:")
        for process in status["processes"]:
            print(
                f"- pid={process['pid']} memory={process['used_memory_mb']}MB "
                f"name={process['process_name']}"
            )
    else:
        print("No compute processes reported by nvidia-smi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
