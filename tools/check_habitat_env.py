from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "habitat_spike" / "habitat_env_status.json"


def main() -> int:
    status = collect_status()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    print(f"Habitat environment status written to {OUTPUT_PATH}")
    return 0


def collect_status() -> dict[str, Any]:
    return {
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "machine": platform.machine(),
        "python_version": sys.version,
        "executable": sys.executable,
        "cwd": str(PROJECT_ROOT),
        "is_windows": platform.system().lower() == "windows",
        "is_wsl": _is_wsl(),
        "is_docker": _is_docker(),
        "env": {
            "HABITAT_SIM_LOG": os.environ.get("HABITAT_SIM_LOG"),
            "MAGNUM_LOG": os.environ.get("MAGNUM_LOG"),
            "DISPLAY": os.environ.get("DISPLAY"),
            "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY"),
            "WSL_DISTRO_NAME": os.environ.get("WSL_DISTRO_NAME"),
            "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "NVIDIA_VISIBLE_DEVICES": os.environ.get("NVIDIA_VISIBLE_DEVICES"),
        },
        "commands": {
            "nvidia_smi": _command_probe(["nvidia-smi"], timeout=10),
            "nvcc": _command_probe(["nvcc", "--version"], timeout=10),
        },
        "python_imports": {
            "habitat_sim": _import_probe("habitat_sim"),
            "habitat": _import_probe("habitat"),
            "habitat.config": _import_probe("habitat.config"),
        },
        "scene_data_dirs": _scene_data_dirs(),
    }


def _scene_data_dirs() -> list[dict[str, Any]]:
    candidates = [
        PROJECT_ROOT / "data",
        PROJECT_ROOT / "data" / "scene_datasets",
        PROJECT_ROOT / "data" / "datasets",
        PROJECT_ROOT / "habitat-lab" / "data",
    ]
    return [
        {
            "path": str(path),
            "exists": path.exists(),
            "is_dir": path.is_dir(),
            "scene_file_count": _count_scene_files(path),
        }
        for path in candidates
    ]


def _count_scene_files(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    suffixes = {".glb", ".ply", ".obj"}
    try:
        return sum(1 for item in path.rglob("*") if item.is_file() and item.suffix.lower() in suffixes)
    except Exception:
        return 0


def _is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        text = Path("/proc/version").read_text(encoding="utf-8", errors="replace").lower()
        return "microsoft" in text or "wsl" in text
    except Exception:
        return False


def _is_docker() -> bool:
    if Path("/.dockerenv").exists():
        return True
    try:
        text = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="replace").lower()
        return "docker" in text or "containerd" in text
    except Exception:
        return False


def _command_probe(command: list[str], timeout: int) -> dict[str, Any]:
    executable = shutil.which(command[0])
    result: dict[str, Any] = {
        "available": executable is not None,
        "executable": executable,
        "command": command,
    }
    if executable is None:
        return result
    try:
        completed = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        result.update(
            {
                "returncode": completed.returncode,
                "stdout_tail": _tail(completed.stdout),
                "stderr_tail": _tail(completed.stderr),
            }
        )
    except subprocess.TimeoutExpired as exc:
        result.update({"timeout": True, "error": str(exc)})
    except Exception as exc:
        result.update({"error": str(exc), "error_type": type(exc).__name__})
    return result


def _import_probe(module_name: str) -> dict[str, Any]:
    try:
        module = __import__(module_name, fromlist=["*"])
        version = getattr(module, "__version__", None)
        if version is None and module_name == "habitat":
            version = getattr(getattr(module, "version", None), "__version__", None)
        return {"importable": True, "version": version}
    except Exception as exc:
        return {"importable": False, "error_type": type(exc).__name__, "error": str(exc)}


def _tail(text: str, max_chars: int = 3000) -> str:
    return text[-max_chars:] if text else ""


if __name__ == "__main__":
    raise SystemExit(main())
