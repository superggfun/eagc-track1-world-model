from __future__ import annotations

import importlib.util
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


OUTPUT_PATH = Path("outputs/virtualhome_spike/env_status.json")


def _load_config_path() -> str:
    env_path = os.environ.get("VIRTUALHOME_SIMULATOR_PATH", "")
    if env_path:
        return env_path
    config_path = Path("config.yaml")
    if not config_path.exists():
        return ""
    current_section = ""
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not raw_line.startswith(" ") and line.endswith(":"):
            current_section = line[:-1]
            continue
        if current_section == "virtualhome" and line.startswith("simulator_path:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def collect_status() -> Dict[str, Any]:
    simulator_path = _load_config_path()
    modules = ["virtualhome", "simulation.unity_simulator.comm_unity"]
    module_status = {}
    for module in modules:
        try:
            module_status[module] = importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:
            module_status[module] = False

    status: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "os": platform.platform(),
        "system": platform.system(),
        "python_version": platform.python_version(),
        "virtualhome_simulator_path": simulator_path,
        "simulator_executable_exists": bool(simulator_path) and Path(simulator_path).exists(),
        "module_import_available": module_status,
        "virtualhome_api_available": any(module_status.values()),
        "success": False,
        "reason": "",
        "download_hint": "",
    }
    if not status["virtualhome_api_available"]:
        status["reason"] = "virtualhome_python_api_not_installed"
        status["download_hint"] = "Install the VirtualHome Python API separately; do not add it to the main requirements.txt."
    elif not simulator_path:
        status["reason"] = "missing_virtualhome_simulator_path"
        status["download_hint"] = "Set VIRTUALHOME_SIMULATOR_PATH or config.yaml virtualhome.simulator_path to the Windows Unity executable."
    elif not status["simulator_executable_exists"]:
        status["reason"] = "missing_virtualhome_executable"
        status["download_hint"] = "Please download VirtualHome Windows Unity Simulator executable and set VIRTUALHOME_SIMULATOR_PATH."
    else:
        status["success"] = True
        status["reason"] = "virtualhome_environment_probe_passed"
    return status


def main() -> int:
    status = collect_status()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"VirtualHome environment status written to {OUTPUT_PATH}")
    if not status["success"]:
        print(f"VirtualHome environment not ready: {status['reason']}")
        return 0
    print("VirtualHome environment probe passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
