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
        self.task = "Explore the room and identify visible objects over time."

    def reset(self) -> Dict[str, Any]:
        self.frames = _load_frames(self.image_dir)
        if self.max_steps is not None:
            self.frames = self.frames[: self.max_steps]
        if not self.frames:
            raise ValueError(f"No sequence frames found in {self.image_dir}. Expected frame_000.png style images.")
        self.index = 0
        return self.observe()

    def observe(self) -> Dict[str, Any]:
        frame = self.frames[self.index]
        text = (
            f"Visual sequence frame {self.index}. Extract visible objects, spatial relations, "
            "and any changed object locations. Do not assume missing objects disappeared."
        )
        return {
            "episode_id": f"visual-sequence-{self.image_dir.name}",
            "task": self.task,
            "text": text,
            "image_path": str(frame),
            "step": self.index,
            "source": "visual_sequence",
            "observation": {
                "text": text,
                "image_path": str(frame),
                "step": self.index,
                "source": "visual_sequence",
            },
            "current_room": self.image_dir.name or "visual_sequence",
            "room": self.image_dir.name or "visual_sequence",
            "topology": [
                {
                    "room": self.image_dir.name or "visual_sequence",
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
