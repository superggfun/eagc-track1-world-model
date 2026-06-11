from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from env_adapters.virtualhome_adapter import convert_files
from tools.check_virtualhome_env import collect_status


DEFAULT_OUTPUT_DIR = Path("outputs/virtualhome_spike")


def _status_template() -> Dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": False,
        "reason": "",
        "error_type": "",
        "error_message": "",
        "simulator_started": False,
        "scene_graph_saved": False,
        "program_log_saved": False,
        "frame_saved": False,
        "converted_world_model_saved": False,
        "converted_episode_log_saved": False,
    }


def run_spike(output_dir: Path, scene_id: int, port: int) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    status = _status_template()
    env_status = collect_status()
    (output_dir / "env_status.json").write_text(json.dumps(env_status, indent=2), encoding="utf-8")
    status.update(
        {
            "virtualhome_simulator_path": env_status.get("virtualhome_simulator_path", ""),
            "port": port,
            "scene_id": scene_id,
        }
    )
    if not env_status.get("success"):
        status["reason"] = env_status.get("reason", "virtualhome_environment_not_ready")
        status["download_hint"] = env_status.get("download_hint", "")
        _write_status(output_dir, status)
        return status

    try:
        comm_module = _import_comm_module()
        UnityCommunication = getattr(comm_module, "UnityCommunication")
        kwargs = {"port": port}
        simulator_path = str(env_status["virtualhome_simulator_path"])
        if simulator_path:
            kwargs["file_name"] = simulator_path
        comm = UnityCommunication(**kwargs)
        status["simulator_started"] = True

        _call_if_exists(comm, "reset", scene_id)
        scene_graph = _get_scene_graph(comm)
        scene_graph_path = output_dir / "scene_graph.json"
        scene_graph_path.write_text(json.dumps(scene_graph, indent=2, ensure_ascii=False), encoding="utf-8")
        status["scene_graph_saved"] = True

        program = _choose_program(scene_graph)
        program_log = {"program": program, "result": "not_executed"}
        render_result = _render_program(comm, program)
        if render_result is not None:
            program_log = {"program": program, "result": render_result}
        program_log_path = output_dir / "program_log.json"
        program_log_path.write_text(json.dumps(program_log, indent=2, ensure_ascii=False), encoding="utf-8")
        status["program_log_saved"] = True

        paths = convert_files(scene_graph_path, program_log_path, output_dir)
        status["converted_world_model_saved"] = paths["world_model"].exists()
        status["converted_episode_log_saved"] = paths["episode_log"].exists()
        status["success"] = True
        status["reason"] = "virtualhome_spike_completed"
    except Exception as exc:  # VirtualHome APIs vary; capture exact failure.
        status["reason"] = "virtualhome_runtime_error"
        status["error_type"] = type(exc).__name__
        status["error_message"] = str(exc)
    finally:
        _write_status(output_dir, status)
    return status


def _import_comm_module() -> Any:
    for module_name in ["simulation.unity_simulator.comm_unity", "virtualhome.simulation.unity_simulator.comm_unity"]:
        try:
            return importlib.import_module(module_name)
        except ImportError:
            continue
    raise ImportError("Could not import VirtualHome UnityCommunication module.")


def _call_if_exists(obj: Any, name: str, *args: Any) -> Any:
    method = getattr(obj, name, None)
    if callable(method):
        return method(*args)
    return None


def _get_scene_graph(comm: Any) -> Dict[str, Any]:
    for method_name in ["environment_graph", "get_scene_graph"]:
        method = getattr(comm, method_name, None)
        if not callable(method):
            continue
        result = method()
        if isinstance(result, tuple) and len(result) >= 2:
            return result[1] if isinstance(result[1], dict) else {"raw_result": result}
        if isinstance(result, dict):
            return result
    raise RuntimeError("VirtualHome communication object does not expose a known scene graph method.")


def _choose_program(scene_graph: Dict[str, Any]) -> List[str]:
    names = {
        str(node.get("class_name", "")).lower()
        for node in scene_graph.get("nodes", [])
        if isinstance(node, dict)
    }
    if "chair" in names:
        return ["<char0> [Walk] <chair> (1)", "<char0> [Sit] <chair> (1)"]
    if "book" in names:
        return ["<char0> [Walk] <book> (1)", "<char0> [Grab] <book> (1)"]
    return ["<char0> [Walk] <living_room> (1)"]


def _render_program(comm: Any, program: List[str]) -> Any:
    for method_name in ["render_script", "execute_script"]:
        method = getattr(comm, method_name, None)
        if callable(method):
            return method(program, recording=False)
    return None


def _write_status(output_dir: Path, status: Dict[str, Any]) -> None:
    status["elapsed_written_at"] = datetime.now(timezone.utc).isoformat()
    (output_dir / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"VirtualHome spike status written to {output_dir / 'status.json'}")
    print(json.dumps(status, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a graceful VirtualHome Windows simulator spike.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--scene", type=int, default=0)
    parser.add_argument("--port", type=int, default=int(os.environ.get("VIRTUALHOME_PORT", "8080")))
    args = parser.parse_args()

    status = run_spike(Path(args.output_dir), args.scene, args.port)
    return 0 if status.get("success") or status.get("reason") in {
        "missing_virtualhome_executable",
        "missing_virtualhome_simulator_path",
        "virtualhome_python_api_not_installed",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
