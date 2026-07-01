from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List


OUTPUT_PATH = Path("outputs/local_runtime_check/gpu_status.txt")
KEYWORDS = ["vllm", "python", "unity", "virtualhome", "virtual home"]


def _run(command: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def collect_report() -> str:
    lines: List[str] = [
        "# Local GPU Runtime Check",
        f"timestamp={datetime.now(timezone.utc).isoformat()}",
        "",
        "## nvidia-smi",
    ]
    smi = _run(["nvidia-smi"])
    lines.append(smi.stdout.strip() or smi.stderr.strip() or "nvidia-smi produced no output")

    lines.extend(["", "## queried gpu memory"])
    gpu_query = _run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
            "--format=csv",
        ]
    )
    lines.append(gpu_query.stdout.strip() or gpu_query.stderr.strip())

    lines.extend(["", "## queried compute processes"])
    compute_query = _run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv",
        ]
    )
    lines.append(compute_query.stdout.strip() or compute_query.stderr.strip())

    lines.extend(["", "## relevant Windows processes"])
    ps = _run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process | Select-Object Id,ProcessName,Path | ConvertTo-Json -Depth 2",
        ]
    )
    process_text = ps.stdout.strip() or ps.stderr.strip()
    relevant = []
    for line in process_text.splitlines():
        lower = line.lower()
        if any(keyword in lower for keyword in KEYWORDS):
            relevant.append(line)
    lines.extend(relevant or ["No obvious vLLM/python/Unity/VirtualHome process lines found in process JSON."])
    return "\n".join(lines) + "\n"


def main() -> int:
    report = collect_report()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Local GPU runtime report written to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
