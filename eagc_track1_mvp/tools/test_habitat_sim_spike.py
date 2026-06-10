from __future__ import annotations

import argparse
import json
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
    status = _run_spike(args, output_dir)
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    legacy_status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    print(f"Habitat-Sim spike status written to {status_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a minimal Habitat-Sim RGB observation spike.")
    parser.add_argument("--scene-path", default="")
    parser.add_argument("--output-dir", default="outputs/habitat_spike")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    return parser.parse_args()


def _run_spike(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    started = time.perf_counter()
    rgb_path = output_dir / "rgb.png"
    scene_path = _find_scene(args.scene_path)
    status: dict[str, Any] = {
        "success": False,
        "scene_path": str(scene_path) if scene_path else "",
        "rgb_saved": False,
        "rgb_path": str(rgb_path),
        "observation_keys": [],
        "frame_shape": [],
        "elapsed_seconds": 0.0,
        "error_type": "",
        "error_message": "",
        "reason": "",
    }
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
            sim.step("turn_left")
            status.update(
                {
                    "success": True,
                    "rgb_saved": rgb_path.exists() and rgb_path.stat().st_size > 0,
                    "frame_shape": list(getattr(rgb, "shape", [])),
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


def _find_scene(scene_path_value: str) -> Path | None:
    if scene_path_value:
        scene_path = _resolve_path(scene_path_value)
        return scene_path if scene_path.exists() else None
    scene_root = PROJECT_ROOT / "data" / "scene_datasets"
    if not scene_root.exists():
        return None
    for item in sorted(scene_root.rglob("*")):
        if item.is_file() and item.suffix.lower() in SCENE_SUFFIXES:
            return item
    return None


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


if __name__ == "__main__":
    raise SystemExit(main())
