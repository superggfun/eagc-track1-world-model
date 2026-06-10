from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENE_SUFFIXES = {".glb", ".ply", ".obj"}


def main() -> int:
    args = parse_args()
    output_dir = _resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "status.json"
    legacy_status_path = output_dir / "habitat_sim_status.json"
    if args.worker:
        status = _run_spike(args, output_dir)
    else:
        status = _run_worker(args, status_path)
    _write_status(status, status_path, legacy_status_path)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    print(f"Habitat-Sim spike status written to {status_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a minimal Habitat-Sim RGB observation spike.")
    parser.add_argument("--scene-path", default="")
    parser.add_argument("--output-dir", default="outputs/habitat_spike")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def _write_status(status: dict[str, Any], status_path: Path, legacy_status_path: Path) -> None:
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    legacy_status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_worker(args: argparse.Namespace, status_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    if status_path.exists():
        status_path.unlink()
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--output-dir",
        args.output_dir,
        "--width",
        str(args.width),
        "--height",
        str(args.height),
    ]
    if args.scene_path:
        command.extend(["--scene-path", args.scene_path])
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.timeout_seconds,
        )
        if completed.returncode == 0 and status_path.exists():
            return json.loads(status_path.read_text(encoding="utf-8"))
        status = _base_status(args, _resolve_path(args.output_dir))
        status.update(
            {
                "success": False,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "error_type": "WorkerProcessFailed",
                "error_message": f"Habitat-Sim worker exited with return code {completed.returncode}.",
                "returncode": completed.returncode,
                "stdout_tail": _tail(completed.stdout),
                "stderr_tail": _tail(completed.stderr),
                "reason": "worker_process_failed",
            }
        )
        return status
    except subprocess.TimeoutExpired as exc:
        status = _base_status(args, _resolve_path(args.output_dir))
        status.update(
            {
                "success": False,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "error_type": "TimeoutExpired",
                "error_message": f"Habitat-Sim worker exceeded {args.timeout_seconds} seconds.",
                "stdout_tail": _tail(exc.stdout if isinstance(exc.stdout, str) else ""),
                "stderr_tail": _tail(exc.stderr if isinstance(exc.stderr, str) else ""),
                "reason": "worker_timeout",
            }
        )
        return status


def _run_spike(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    started = time.perf_counter()
    scene_path = _find_scene(args.scene_path)
    status = _base_status(args, output_dir, scene_path)
    rgb_path = Path(status["rgb_path"])
    rgb_step_path = Path(status["rgb_step_path"])
    if scene_path is None:
        status.update(
            {
                "reason": "missing_scene_assets",
                "error_message": "No scene path was provided and no .glb/.ply/.obj scene files were found under data/scene_datasets/.",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
        )
        return status
    try:
        import habitat_sim
        from habitat_sim.utils.common import d3_40_colors_rgb  # noqa: F401

        sim_cfg = habitat_sim.SimulatorConfiguration()
        sim_cfg.scene_id = str(scene_path)

        sensor_spec = habitat_sim.CameraSensorSpec()
        sensor_spec.uuid = "color_sensor"
        sensor_spec.sensor_type = habitat_sim.SensorType.COLOR
        sensor_spec.resolution = [args.height, args.width]
        sensor_spec.position = [0.0, 1.5, 0.0]

        agent_cfg = habitat_sim.agent.AgentConfiguration()
        agent_cfg.sensor_specifications = [sensor_spec]
        agent_cfg.action_space = {
            "move_forward": habitat_sim.agent.ActionSpec(
                "move_forward", habitat_sim.agent.ActuationSpec(amount=0.25)
            ),
            "turn_left": habitat_sim.agent.ActionSpec(
                "turn_left", habitat_sim.agent.ActuationSpec(amount=10.0)
            ),
        }

        cfg = habitat_sim.Configuration(sim_cfg, [agent_cfg])
        sim = habitat_sim.Simulator(cfg)
        try:
            observations = sim.get_sensor_observations()
            status["observation_keys"] = sorted(str(key) for key in observations.keys())
            rgb = observations.get("color_sensor")
            if rgb is None:
                raise RuntimeError("Habitat-Sim returned no color_sensor observation.")
            _save_rgb(rgb, rgb_path)
            step_observations = sim.step("turn_left")
            step_rgb = step_observations.get("color_sensor")
            if step_rgb is None:
                raise RuntimeError("Habitat-Sim action step returned no color_sensor observation.")
            _save_rgb(step_rgb, rgb_step_path)
            status.update(
                {
                    "success": True,
                    "rgb_saved": rgb_path.exists() and rgb_path.stat().st_size > 0,
                    "action_step_success": rgb_step_path.exists() and rgb_step_path.stat().st_size > 0,
                    "frame_shape": list(getattr(rgb, "shape", [])),
                    "step_frame_shape": list(getattr(step_rgb, "shape", [])),
                    "reason": "",
                }
            )
        finally:
            sim.close()
    except Exception as exc:
        status.update(
            {
                "success": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
                "rgb_saved": rgb_path.exists() and rgb_path.stat().st_size > 0,
            }
        )
    finally:
        status["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    return status


def _base_status(args: argparse.Namespace, output_dir: Path, scene_path: Path | None = None) -> dict[str, Any]:
    if scene_path is None:
        scene_path = _find_scene(args.scene_path)
    rgb_path = output_dir / "rgb.png"
    rgb_step_path = output_dir / "rgb_step_001.png"
    return {
        "success": False,
        "scene_path": str(scene_path) if scene_path else "",
        "rgb_saved": False,
        "rgb_path": str(rgb_path),
        "rgb_step_path": str(rgb_step_path),
        "action_step_success": False,
        "observation_keys": [],
        "frame_shape": [],
        "step_frame_shape": [],
        "elapsed_seconds": 0.0,
        "error_type": "",
        "error_message": "",
        "reason": "",
    }


def _find_scene(scene_path_value: str) -> Path | None:
    if scene_path_value:
        scene_path = _resolve_path(scene_path_value)
        return scene_path if scene_path.exists() else None
    for root in (PROJECT_ROOT / "data" / "scene_datasets", PROJECT_ROOT / "data" / "versioned_data"):
        for item in _walk_scene_files(root):
            return item
    return None


def _walk_scene_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=True):
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() in SCENE_SUFFIXES:
                files.append(path)
    return sorted(files)


def _save_rgb(rgb: Any, path: Path) -> None:
    try:
        from PIL import Image

        Image.fromarray(rgb).save(path)
    except Exception as exc:
        raise RuntimeError(f"Failed to save RGB observation as PNG: {exc}") from exc


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _tail(text: str, max_chars: int = 5000) -> str:
    return text[-max_chars:] if text else ""


if __name__ == "__main__":
    raise SystemExit(main())
