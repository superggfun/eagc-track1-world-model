from __future__ import annotations

import importlib.util
import json
import os
import platform
import sys
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


def _load_config_value(section: str, key: str, default: str = "") -> str:
    config_path = Path("config.yaml")
    if not config_path.exists():
        return default
    current_section = ""
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not raw_line.startswith(" ") and line.endswith(":"):
            current_section = line[:-1]
            continue
        if current_section == section and line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return default


def get_virtualhome_repo_path() -> str:
    return os.environ.get("VIRTUALHOME_REPO_PATH", "").strip()


def get_virtualhome_simulator_path() -> str:
    return _load_config_path()


def _prepare_repo_import_path(repo_path: str) -> bool:
    if not repo_path:
        return False
    root = Path(repo_path)
    candidates = [
        root,
        root / "virtualhome",
        root / "simulation",
    ]
    added = False
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            value = str(candidate.resolve())
            if value not in sys.path:
                sys.path.insert(0, value)
            added = True
    return added


def _module_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def collect_status() -> Dict[str, Any]:
    repo_path = get_virtualhome_repo_path()
    repo_path_added = _prepare_repo_import_path(repo_path)
    simulator_path = get_virtualhome_simulator_path()
    port = os.environ.get("VIRTUALHOME_PORT", "") or _load_config_value("virtualhome", "port", "8080")
    default_scene = _load_config_value("virtualhome", "default_scene", "0")
    camera_mode = _load_config_value("virtualhome", "camera_mode", "FIRST_PERSON")
    modules = ["virtualhome", "simulation.unity_simulator.comm_unity"]
    module_status = {}
    for module in modules:
        module_status[module] = _module_available(module)

    executable_path = Path(simulator_path) if simulator_path else None
    executable_exists = bool(executable_path and executable_path.exists())
    executable_size = executable_path.stat().st_size if executable_exists and executable_path else None

    status: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "os": platform.platform(),
        "system": platform.system(),
        "python_version": platform.python_version(),
        "virtualhome_repo_path": repo_path,
        "virtualhome_repo_path_exists": bool(repo_path) and Path(repo_path).exists(),
        "virtualhome_repo_path_added_to_pythonpath": repo_path_added,
        "virtualhome_simulator_path": simulator_path,
        "virtualhome_port": port,
        "virtualhome_default_scene": default_scene,
        "virtualhome_camera_mode": camera_mode,
        "simulator_executable_exists": executable_exists,
        "simulator_executable_size_bytes": executable_size,
        "module_import_available": module_status,
        "virtualhome_api_available": any(module_status.values()),
        "success": False,
        "reason": "",
        "download_hint": "",
    }
    if not status["virtualhome_api_available"]:
        status["reason"] = "missing_virtualhome_python_api"
        status["download_hint"] = (
            "Clone or locate the VirtualHome repository, then set VIRTUALHOME_REPO_PATH "
            "or install it editable in a separate environment. Do not add it to requirements.txt."
        )
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
