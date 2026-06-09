from pathlib import Path
from typing import Any, Dict

from env_adapters.mock_env import MockEnv


class VisualMockEnv(MockEnv):
    """Single-image smoke environment for validating the vision interface."""

    def __init__(self, image_path: str | Path) -> None:
        super().__init__("mock-bedroom-relocated")
        self.visual_episode_id = "visual-bedroom-smoke"
        self.image_path = str(image_path)

    def reset(self) -> Dict[str, Any]:
        packet = super().reset()
        packet["episode_id"] = self.visual_episode_id
        packet["task"] = "Find the book and place it on the chair."
        packet["text"] = "A bedroom scene image is provided. Extract visible objects and spatial relations."
        packet["image_path"] = self.image_path
        packet["observation"] = {
            "text": packet["text"],
            "image_path": self.image_path,
        }
        return packet
