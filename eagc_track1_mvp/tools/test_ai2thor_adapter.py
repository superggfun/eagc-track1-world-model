import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from env_adapters.ai2thor_adapter import AI2ThorAdapter, AI2ThorAdapterError  # noqa: E402


def main() -> int:
    args = parse_args()
    output_dir = PROJECT_ROOT / "outputs" / "ai2thor_smoke"

    try:
        import ai2thor  # noqa: F401
    except ImportError:
        print("AI2-THOR is not installed. Install it with:")
        print("pip install ai2thor")
        return 1

    adapter = AI2ThorAdapter(
        output_dir=output_dir,
        scene=args.scene,
        frame_name="frame.png",
        metadata_name="metadata.json",
    )
    try:
        packet = adapter.reset(args.scene)
        metadata_path = Path(packet["metadata_path"])
        frame_path = Path(packet["image_path"])
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        objects = metadata.get("objects", []) if isinstance(metadata, dict) else []
        visible_objects = [obj for obj in objects if isinstance(obj, dict) and obj.get("visible")]
        frame_shape = _frame_shape(adapter.event.frame)

        print(f"scene: {args.scene}")
        print(f"frame shape: {frame_shape}")
        print(f"number of metadata objects: {len(objects)}")
        print(f"number of visible objects: {len(visible_objects)}")
        print(f"frame path: {frame_path}")
        print(f"metadata path: {metadata_path}")
        return 0
    except AI2ThorAdapterError as exc:
        print(f"AI2-THOR smoke failed: {exc}")
        return 1
    except Exception as exc:
        print(f"AI2-THOR smoke failed with unexpected error: {exc}")
        return 1
    finally:
        adapter.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test AI2-THOR Controller frame capture.")
    parser.add_argument("--scene", default="FloorPlan1", help="AI2-THOR scene name.")
    return parser.parse_args()


def _frame_shape(frame: object) -> str:
    shape = getattr(frame, "shape", None)
    if shape is None:
        return "unknown"
    return "x".join(str(item) for item in shape)


if __name__ == "__main__":
    raise SystemExit(main())
