from pathlib import Path
from typing import Any, Dict, List

from env_adapters.base import BaseEnvAdapter


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class VisualSequenceEnv(BaseEnvAdapter):
    """Multi-image local visual sequence used for incremental world-model smoke tests."""

    def __init__(self, image_dir: str | Path, max_steps: int | None = None) -> None:
        self.image_dir = Path(image_dir)
        self.max_steps = max_steps
        self.frames: List[Path] = []
        self.index = 0
        self.task = "Build and maintain a world model from multiple visual observations."

    def reset(self) -> Dict[str, Any]:
        self.frames = _load_frames(self.image_dir)
        if self.max_steps is not None:
            self.frames = self.frames[: self.max_steps]
        if not self.frames:
            if not self.image_dir.exists() or not self.image_dir.is_dir():
                raise ValueError(
                    f"Visual sequence image directory does not exist: {self.image_dir}. "
                    "Create it and add local frame_000.jpg/frame_000.png style images."
                )
            raise ValueError(
                f"No visual sequence frames found in {self.image_dir}. "
                "Expected local images named frame_000.jpg, frame_001.png, and so on."
            )
        self.index = 0
        return self.observe()

    def observe(self) -> Dict[str, Any]:
        frame = self.frames[self.index]
        text = (
            "A visual observation frame is provided. Extract visible objects, spatial relations, "
            "object states, uncertainty, and update the world model incrementally."
        )
        room = _sequence_room_name(self.image_dir)
        return {
            "episode_id": f"visual-sequence-{room}",
            "step": self.index,
            "task": self.task,
            "text": text,
            "image_path": str(frame),
            "source": "visual_sequence",
            "observation": {
                "text": text,
                "image_path": str(frame),
                "step": self.index,
                "source": "visual_sequence",
            },
            "current_room": room,
            "room": room,
            "topology": [
                {
                    "room": room,
                    "node_type": "visual_sequence",
                    "visited": True,
                    "frontiers": [],
                }
            ],
            "object_hints": {},
            "visible_objects": [],
        }

    def step(self, action: str) -> Dict[str, Any]:
        if action != "next_frame":
            return {"success": True, "result": "success", "message": f"Ignored sequence action {action}."}
        if self.index + 1 >= len(self.frames):
            return {"success": False, "result": "end_of_sequence", "message": "No more visual sequence frames."}
        self.index += 1
        packet = self.observe()
        return {"success": True, "result": "success", "message": "Advanced to next frame.", "observation": packet}

    @property
    def frame_count(self) -> int:
        return len(self.frames)


def _load_frames(image_dir: Path) -> List[Path]:
    if not image_dir.exists() or not image_dir.is_dir():
        return []
    frames = [
        path
        for path in image_dir.iterdir()
        if path.is_file() and path.name.lower().startswith("frame_") and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(frames, key=lambda path: path.name.lower())


def _sequence_room_name(image_dir: Path) -> str:
    name = image_dir.name or "visual_sequence"
    if name.endswith("_sequence"):
        name = name[: -len("_sequence")]
    return name or "visual_sequence"
