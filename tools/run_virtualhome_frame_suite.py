from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "virtualhome_spike"
STATUS_PATH = OUTPUT_DIR / "frame_suite_status.json"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report: Dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": False,
        "skipped": False,
        "reason": "",
        "port": 8080,
        "commands": [],
    }
    if not _is_port_open("127.0.0.1", 8080):
        report.update(
            {
                "success": True,
                "skipped": True,
                "reason": "virtualhome_manual_play_port_not_open",
                "hint": "Start VirtualHome.exe manually, choose Windowed mode if prompted, press Play, then rerun this tier.",
            }
        )
        _write_report(report)
        print("VirtualHome frame tier skipped: 127.0.0.1:8080 is not listening.")
        return 0

    commands = [
        [sys.executable, "tools/test_virtualhome_windows_spike.py", "--export-frame"],
        [sys.executable, "-m", "validators.validate_virtualhome_spike", "outputs/virtualhome_spike/status.json"],
        [
            sys.executable,
            "-m",
            "validators.validate_virtualhome_converted_world_model",
            "outputs/virtualhome_spike/converted_world_model.json",
            "outputs/virtualhome_spike/converted_episode_log.jsonl",
        ],
        [
            sys.executable,
            "-m",
            "validators.validate_virtualhome_frame_export",
            "outputs/virtualhome_spike/frame_export_status.json",
        ],
        [sys.executable, "tools/build_virtualhome_evidence_report.py"],
    ]
    report["commands"] = [_run(command) for command in commands]
    report["success"] = all(item.get("returncode") == 0 for item in report["commands"] if isinstance(item, dict))
    report["reason"] = "virtualhome_frame_suite_passed" if report["success"] else "virtualhome_frame_suite_failed"
    _write_report(report)
    return 0 if report["success"] else 1


def _run(command: List[str]) -> Dict[str, object]:
    print(f"\n$ {' '.join(command)}", flush=True)
    timer = time.perf_counter()
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    return {
        "command": " ".join(command),
        "returncode": completed.returncode,
        "elapsed_seconds": round(time.perf_counter() - timer, 3),
    }


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def _write_report(report: Dict[str, object]) -> None:
    STATUS_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VirtualHome frame suite report written to {STATUS_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
