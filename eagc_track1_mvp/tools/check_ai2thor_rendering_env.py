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
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "ai2thor_render_test" / "env_diagnostics.json"


def main() -> int:
    diagnostics = collect_diagnostics()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    print(f"AI2-THOR rendering environment diagnostics written to {OUTPUT_PATH}")
    return 0


def collect_diagnostics() -> dict[str, Any]:
    data: dict[str, Any] = {
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "machine": platform.machine(),
        "python_version": sys.version,
        "executable": sys.executable,
        "cwd": str(PROJECT_ROOT),
        "is_wsl": _is_wsl(),
        "is_docker": _is_docker(),
        "env": {
            "DISPLAY": os.environ.get("DISPLAY"),
            "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY"),
            "WSL_DISTRO_NAME": os.environ.get("WSL_DISTRO_NAME"),
            "NVIDIA_VISIBLE_DEVICES": os.environ.get("NVIDIA_VISIBLE_DEVICES"),
            "NVIDIA_DRIVER_CAPABILITIES": os.environ.get("NVIDIA_DRIVER_CAPABILITIES"),
        },
        "commands": {},
        "python_imports": {},
    }
    data["commands"]["nvidia_smi"] = _command_probe(["nvidia-smi"], timeout=10)
    data["commands"]["docker_version"] = _command_probe(["docker", "--version"], timeout=10)
    data["commands"]["docker_gpus_all"] = _docker_gpu_probe()
    data["commands"]["glxinfo"] = _command_probe(["glxinfo", "-B"], timeout=10)
    data["commands"]["xvfb_run"] = _command_probe(["xvfb-run", "--help"], timeout=10)
    data["python_imports"]["ai2thor"] = _import_probe("ai2thor", version_attr="__version__")
    data["python_imports"]["ai2thor.controller.Controller"] = _import_symbol_probe(
        "ai2thor.controller", "Controller"
    )
    data["python_imports"]["ai2thor.platform.CloudRendering"] = _import_symbol_probe(
        "ai2thor.platform", "CloudRendering"
    )
    return data


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


def _docker_gpu_probe() -> dict[str, Any]:
    if shutil.which("docker") is None:
        return {"available": False, "reason": "docker command not found"}
    return _command_probe(
        [
            "docker",
            "run",
            "--rm",
            "--gpus",
            "all",
            "nvidia/cuda:12.4.1-base-ubuntu22.04",
            "nvidia-smi",
        ],
        timeout=60,
    )


def _import_probe(module_name: str, version_attr: str | None = None) -> dict[str, Any]:
    try:
        module = __import__(module_name, fromlist=["*"])
        result: dict[str, Any] = {"importable": True}
        if version_attr:
            result["version"] = getattr(module, version_attr, None)
        return result
    except Exception as exc:
        return {"importable": False, "error_type": type(exc).__name__, "error": str(exc)}


def _import_symbol_probe(module_name: str, symbol_name: str) -> dict[str, Any]:
    try:
        module = __import__(module_name, fromlist=[symbol_name])
        symbol = getattr(module, symbol_name)
        return {"importable": True, "symbol": repr(symbol)}
    except Exception as exc:
        return {"importable": False, "error_type": type(exc).__name__, "error": str(exc)}


def _tail(text: str, max_chars: int = 3000) -> str:
    return text[-max_chars:] if text else ""


if __name__ == "__main__":
    raise SystemExit(main())
