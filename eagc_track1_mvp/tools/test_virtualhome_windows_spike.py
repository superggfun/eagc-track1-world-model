from __future__ import annotations

import argparse
import importlib
import json
import os
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
        kwargs = {"port": str(port), "logging": False}
        simulator_path = str(env_status["virtualhome_simulator_path"])
        if simulator_path:
            kwargs["file_name"] = simulator_path
        manual_proc: subprocess.Popen[Any] | None = None
        try:
            if _is_port_open("127.0.0.1", port):
                status["existing_simulator_connection_used"] = True
                comm = UnityCommunication(port=str(port), logging=False)
            else:
                comm = UnityCommunication(**kwargs)
        except Exception as exc:
            if _can_fallback_manual_launch(exc, simulator_path):
                manual_proc = _launch_windows_simulator(simulator_path, port, output_dir)
                _wait_for_port("127.0.0.1", port, timeout_seconds=60)
                status["manual_windows_launch_used"] = True
                status["manual_windows_launch_pid"] = manual_proc.pid
                comm = UnityCommunication(port=str(port))
            else:
                raise
        status["simulator_started"] = True

        _call_if_exists(comm, "reset", scene_id)
        character_result = _call_if_exists(comm, "add_character")
        status["character_added"] = _virtualhome_success(character_result)
        status["character_add_result"] = character_result
        scene_graph = _get_scene_graph(comm)
        scene_graph_path = output_dir / "scene_graph.json"
        scene_graph_path.write_text(json.dumps(scene_graph, indent=2, ensure_ascii=False), encoding="utf-8")
        status["scene_graph_saved"] = True

        program = _choose_program(scene_graph)
        program_log = {"program": program, "result": "not_executed"}
        render_result = _render_program(comm, program)
        if render_result is not None:
            program_log = {"program": program, "result": render_result}
        status["program_execution_success"] = _virtualhome_success(render_result)
        program_log_path = output_dir / "program_log.json"
        program_log_path.write_text(json.dumps(program_log, indent=2, ensure_ascii=False), encoding="utf-8")
        status["program_log_saved"] = True
        frame_path = _try_save_frame(comm, output_dir)
        status["frame_saved"] = frame_path is not None
        if frame_path:
            status["frame_path"] = str(frame_path)

        paths = convert_files(scene_graph_path, program_log_path, output_dir)
        status["converted_world_model_saved"] = paths["world_model"].exists()
        status["converted_episode_log_saved"] = paths["episode_log"].exists()
        converted_world_model = json.loads(paths["world_model"].read_text(encoding="utf-8"))
        converted_objects = converted_world_model.get("objects", [])
        status["converted_object_count"] = len(converted_objects) if isinstance(converted_objects, list) else 0
        if status["converted_object_count"] <= 0:
            raise RuntimeError("VirtualHome scene graph conversion produced no world_model objects.")
        if render_result is not None and not _virtualhome_success(render_result):
            raise RuntimeError(f"VirtualHome program execution failed: {render_result}")
        status["success"] = True
        status["reason"] = "virtualhome_spike_completed"
    except Exception as exc:  # VirtualHome APIs vary; capture exact failure.
        if isinstance(exc, TimeoutError):
            status["reason"] = "virtualhome_simulator_connection_timeout"
            status["manual_start_hint"] = (
                "The Windows executable exists and can be launched, but the Python API could not connect "
                "to the HTTP port. Try starting VirtualHome.exe manually, choose Windowed mode if prompted, "
                "press Play, then rerun this smoke."
            )
        else:
            status["reason"] = "virtualhome_runtime_error"
        status["error_type"] = type(exc).__name__
        status["error_message"] = str(exc)
    finally:
        if "manual_proc" in locals() and manual_proc is not None and manual_proc.poll() is None:
            manual_proc.terminate()
            try:
                manual_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                manual_proc.kill()
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


def _can_fallback_manual_launch(exc: Exception, simulator_path: str) -> bool:
    if not simulator_path or os.name != "nt":
        return False
    message = str(exc).lower()
    return "could not be launched" in message or "environment was found" in message


def _launch_windows_simulator(simulator_path: str, port: int, output_dir: Path) -> subprocess.Popen[Any]:
    exe = Path(simulator_path)
    log_path = output_dir / f"VirtualHome_Player_{port}.log"
    args = [
        str(exe),
        "-screen-fullscreen",
        "0",
        "-screen-quality",
        "4",
        f"-http-port={port}",
        "-logFile",
        str(log_path),
    ]
    return subprocess.Popen(
        args,
        cwd=str(exe.parent),
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_for_port(host: str, port: int, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            try:
                sock.connect((host, port))
                return
            except OSError as exc:
                last_error = str(exc)
        time.sleep(1.0)
    raise TimeoutError(f"VirtualHome simulator did not open {host}:{port} within {timeout_seconds}s. Last error: {last_error}")


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


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
    nodes = [node for node in scene_graph.get("nodes", []) if isinstance(node, dict)]
    names = {str(node.get("class_name", "")).lower() for node in nodes}
    for target_name, actions in [
        ("sofa", ["Walk", "Sit"]),
        ("television", ["Walk"]),
        ("tv", ["Walk"]),
        ("book", ["Find"]),
        ("chair", ["Find"]),
    ]:
        if target_name in names:
            return [f"<char0> [{action}] <{target_name}> (1)" for action in actions]
    room = next((node for node in nodes if _node_category_name(node) == "rooms"), None)
    if room and room.get("id") is not None:
        room_name = str(room.get("class_name") or "living_room").lower()
        return [f"<char0> [Walk] <{room_name}> ({room['id']})"]
    return ["<char0> [Walk] <living_room> (1)"]


def _first_node_id(nodes: List[Dict[str, Any]], class_name: str) -> Any:
    for node in nodes:
        if str(node.get("class_name", "")).lower() == class_name and node.get("id") is not None:
            return node["id"]
    return None


def _node_category_name(node: Dict[str, Any]) -> str:
    return str(node.get("category") or "").lower()


def _render_program(comm: Any, program: List[str]) -> Any:
    method = getattr(comm, "render_script", None)
    if callable(method):
        return method(program, recording=False, skip_animation=True, find_solution=True, processing_time_limit=10)
    method = getattr(comm, "execute_script", None)
    if callable(method):
        return method(program)
    return None


def _virtualhome_success(result: Any) -> bool:
    if isinstance(result, tuple) and result:
        return result[0] is True
    if isinstance(result, list) and result:
        return result[0] is True
    if isinstance(result, dict):
        value = result.get("success")
        if isinstance(value, bool):
            return value
    return result is True


def _try_save_frame(comm: Any, output_dir: Path) -> Path | None:
    for method_name in ["camera_image", "get_camera_image", "get_image", "screenshot"]:
        method = getattr(comm, method_name, None)
        if not callable(method):
            continue
        try:
            result = method()
        except Exception:
            continue
        payload = _extract_frame_payload(result)
        if not payload:
            continue
        frame_path = output_dir / "frame_000.png"
        frame_path.write_bytes(payload)
        return frame_path
    return None


def _extract_frame_payload(result: Any) -> bytes | None:
    if isinstance(result, bytes):
        return result
    if isinstance(result, tuple):
        for item in result:
            payload = _extract_frame_payload(item)
            if payload:
                return payload
    if isinstance(result, dict):
        for key in ["image", "frame", "png", "bytes"]:
            payload = _extract_frame_payload(result.get(key))
            if payload:
                return payload
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
        "missing_virtualhome_python_api",
        "missing_virtualhome_simulator_path",
        "virtualhome_python_api_not_installed",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
