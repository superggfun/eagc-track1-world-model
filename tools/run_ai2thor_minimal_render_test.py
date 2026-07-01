from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import time
import traceback
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
    output_dir = _resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "status.json"

    started = time.perf_counter()
    queue: mp.Queue[dict[str, Any]] = mp.Queue()
    process = mp.Process(
        target=_render_worker,
        args=(args.scene, args.platform, args.width, args.height, str(output_dir), queue),
    )
    process.start()
    process.join(args.timeout_seconds)

    if process.is_alive():
        process.terminate()
        process.join(10)
        status = _base_status(args, started)
        status.update(
            {
                "success": False,
                "error_type": "TimeoutExpired",
                "error_message": f"AI2-THOR render test exceeded {args.timeout_seconds} seconds.",
                "frame_saved": False,
                "metadata_saved": False,
                "object_count": 0,
                "visible_object_count": 0,
            }
        )
    else:
        try:
            status = queue.get_nowait()
        except Exception:
            status = _base_status(args, started)
            status.update(
                {
                    "success": False,
                    "error_type": "WorkerNoStatus",
                    "error_message": f"Worker exited with code {process.exitcode} without status payload.",
                    "frame_saved": False,
                    "metadata_saved": False,
                    "object_count": 0,
                    "visible_object_count": 0,
                }
            )
        status["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        status["worker_exitcode"] = process.exitcode

    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    print(f"AI2-THOR render status written to {status_path}")
    return 0 if status.get("success") else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a timeout-safe minimal AI2-THOR render test.")
    parser.add_argument("--scene", default="FloorPlan1")
    parser.add_argument("--platform", choices=["default", "cloud"], default="default")
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=600)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--output-dir", default="outputs/ai2thor_render_test")
    return parser.parse_args()


def _render_worker(
    scene: str,
    platform_name: str,
    width: int,
    height: int,
    output_dir_value: str,
    queue: mp.Queue[dict[str, Any]],
) -> None:
    started = time.perf_counter()
    output_dir = Path(output_dir_value)
    frame_path = output_dir / "frame.png"
    metadata_path = output_dir / "metadata.json"
    controller: Any = None
    status: dict[str, Any] = {
        "success": False,
        "platform": platform_name,
        "scene": scene,
        "width": width,
        "height": height,
        "elapsed_seconds": 0.0,
        "error_type": "",
        "error_message": "",
        "frame_saved": False,
        "metadata_saved": False,
        "object_count": 0,
        "visible_object_count": 0,
        "frame_path": str(frame_path),
        "metadata_path": str(metadata_path),
    }
    try:
        from ai2thor.controller import Controller

        kwargs: dict[str, Any] = {"scene": scene, "width": width, "height": height}
        if platform_name == "cloud":
            from ai2thor.platform import CloudRendering

            kwargs["platform"] = CloudRendering
        controller = Controller(**kwargs)
        event = controller.last_event
        frame = getattr(event, "frame", None)
        if frame is None:
            raise RuntimeError("Controller started but event.frame is missing.")
        from PIL import Image

        Image.fromarray(frame).save(frame_path)
        metadata = _to_jsonable(getattr(event, "metadata", {}))
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        objects = metadata.get("objects", []) if isinstance(metadata, dict) else []
        visible_objects = [item for item in objects if isinstance(item, dict) and item.get("visible")]
        status.update(
            {
                "success": True,
                "frame_saved": frame_path.exists() and frame_path.stat().st_size > 0,
                "metadata_saved": metadata_path.exists() and metadata_path.stat().st_size > 0,
                "object_count": len(objects),
                "visible_object_count": len(visible_objects),
                "frame_shape": list(getattr(frame, "shape", [])),
            }
        )
    except Exception as exc:
        status.update(
            {
                "success": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
                "frame_saved": frame_path.exists() and frame_path.stat().st_size > 0,
                "metadata_saved": metadata_path.exists() and metadata_path.stat().st_size > 0,
            }
        )
    finally:
        if controller is not None:
            try:
                controller.stop()
            except Exception:
                pass
        status["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        queue.put(status)


def _base_status(args: argparse.Namespace, started: float) -> dict[str, Any]:
    output_dir = _resolve_path(args.output_dir)
    return {
        "success": False,
        "platform": args.platform,
        "scene": args.scene,
        "width": args.width,
        "height": args.height,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "frame_path": str(output_dir / "frame.png"),
        "metadata_path": str(output_dir / "metadata.json"),
    }


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
