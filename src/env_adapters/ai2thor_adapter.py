import json
from pathlib import Path
from typing import Any, Dict

from env_adapters.base import BaseEnvAdapter, adapter_capabilities


class AI2ThorAdapterError(RuntimeError):
    pass


class AI2ThorAdapter(BaseEnvAdapter):
    """Minimal AI2-THOR adapter used for simulator smoke tests."""

    def __init__(
        self,
        output_dir: Path,
        scene: str = "FloorPlan1",
        oracle_metadata_mode: bool = False,
        frame_name: str = "simulator_frame.png",
        metadata_name: str = "simulator_metadata.json",
    ) -> None:
        self.output_dir = output_dir
        self.scene = scene
        self.oracle_metadata_mode = oracle_metadata_mode
        self.controller: Any = None
        self.event: Any = None
        self.frame_path = self.output_dir / frame_name
        self.metadata_path = self.output_dir / metadata_name
        self.oracle_objects_path = self.output_dir / "debug_oracle_objects.json"
        self.start_success = False
        self.error_message = ""

    def reset(self, scene: str | None = None) -> Dict[str, Any]:
        if scene:
            self.scene = scene
        self.output_dir.mkdir(parents=True, exist_ok=True)
        try:
            from ai2thor.controller import Controller

            self.controller = Controller(scene=self.scene)
            self.event = self.controller.last_event
            self.start_success = True
            self.error_message = ""
            return self.observe()
        except Exception as exc:
            self.start_success = False
            self.error_message = str(exc)
            self.close()
            raise AI2ThorAdapterError(
                "Failed to start AI2-THOR Controller. "
                f"scene={self.scene}, error={exc}"
            ) from exc

    def observe(self) -> Dict[str, Any]:
        if self.event is None:
            raise AI2ThorAdapterError("AI2-THOR adapter has no event. Call reset() first.")
        metadata = _to_jsonable(getattr(self.event, "metadata", {}))
        self._save_frame(getattr(self.event, "frame", None))
        self.metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        if self.oracle_metadata_mode:
            objects = metadata.get("objects", []) if isinstance(metadata, dict) else []
            self.oracle_objects_path.write_text(
                json.dumps(objects, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        return {
            "episode_id": f"ai2thor-smoke-{self.scene}",
            "task": "Explore the room and identify visible objects.",
            "text": (
                "An AI2-THOR simulator frame is provided. Extract visible objects, "
                "spatial relations, and room information."
            ),
            "image_path": str(self.frame_path),
            "metadata_path": str(self.metadata_path),
            "source": "ai2thor",
            "observation": {
                "text": (
                    "An AI2-THOR simulator frame is provided. Extract visible objects, "
                    "spatial relations, and room information."
                ),
                "image_path": str(self.frame_path),
                "metadata_path": str(self.metadata_path),
                "source": "ai2thor",
            },
            "current_room": self.scene,
            "room": self.scene,
            "topology": [
                {
                    "room": self.scene,
                    "node_type": "simulator_scene",
                    "visited": True,
                    "frontiers": [],
                }
            ],
            "object_hints": {},
            "visible_objects": [],
        }

    def step(self, action: str) -> Dict[str, Any]:
        return {
            "success": False,
            "result": "unsupported",
            "reason": "ai2thor_action_execution_not_validated",
            "message": (
                "AI2-THOR action execution is reserved but not validated in this project. "
                f"Requested action: {action}"
            ),
        }

    def get_scene_graph(self) -> Dict[str, Any]:
        if self.event is None:
            return {
                "success": False,
                "reason": "ai2thor_not_started",
                "message": "Call reset() first; AI2-THOR rendering is not validated on the current local/remote environments.",
            }
        metadata = _to_jsonable(getattr(self.event, "metadata", {}))
        return {
            "success": True,
            "source": "ai2thor_metadata",
            "scene_graph": metadata,
        }

    def capture_frame(self) -> Dict[str, Any]:
        if self.event is None:
            return {
                "success": False,
                "reason": "ai2thor_not_started",
                "message": "Call reset() first; AI2-THOR rendering is not validated on the current local/remote environments.",
            }
        self._save_frame(getattr(self.event, "frame", None))
        return {"success": True, "frame_path": str(self.frame_path)}

    def capabilities(self) -> Dict[str, Any]:
        return adapter_capabilities(
            adapter_name="ai2thor",
            validated=False,
            validation_status="reserved_not_validated",
            requires_rendering=True,
            supports_scene_graph=True,
            supports_frame_export=True,
            supports_action_execution=False,
            supports_online_closed_loop=False,
            known_blockers=["Windows/WSL/cloud rendering stack unresolved"],
        )

    def close(self) -> None:
        if self.controller is not None:
            try:
                self.controller.stop()
            except Exception as exc:
                self.error_message = f"AI2-THOR controller.stop() failed during close(): {type(exc).__name__}: {exc}"
            finally:
                self.controller = None

    def _save_frame(self, frame: Any) -> None:
        if frame is None:
            raise AI2ThorAdapterError("AI2-THOR event.frame is missing.")
        try:
            from PIL import Image

            image = Image.fromarray(frame)
            image.save(self.frame_path)
        except Exception as exc:
            raise AI2ThorAdapterError(f"Failed to save AI2-THOR frame: {exc}") from exc


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
