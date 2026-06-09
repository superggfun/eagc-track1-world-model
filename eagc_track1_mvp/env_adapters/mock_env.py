from typing import Any, Dict, List

from env_adapters.base import BaseEnvAdapter


class MockEnv(BaseEnvAdapter):
    """Text-only indoor scene used until the official EAGC runtime exists."""

    def __init__(self) -> None:
        self.episode_id = "mock-bedroom-001"
        self.room = "bedroom"
        self.visible_objects: List[str] = ["bed", "pillow", "book", "lamp", "chair", "door"]
        self.task = "Find the book and place it on the chair."
        self.step_count = 0
        self.book_location = "bed"
        self.pick_up_attempts = 0

    def reset(self) -> Dict[str, Any]:
        self.step_count = 0
        self.book_location = "bed"
        self.pick_up_attempts = 0
        return {
            "episode_id": self.episode_id,
            "task": self.task,
            "observation": self._observation_text(),
            "room": self.room,
            "visible_objects": list(self.visible_objects),
        }

    def step(self, action: str) -> Dict[str, Any]:
        self.step_count += 1

        if action == "pick_up(book)":
            self.pick_up_attempts += 1

        if action == "pick_up(book)" and self.pick_up_attempts == 1:
            self.book_location = "unknown"
            return {
                "success": False,
                "result": "failure",
                "message": "Attempted pick_up(book), but the book is no longer on the bed.",
                "exception": {
                    "type": "object_location_changed",
                    "object": "book",
                    "state": "location unknown",
                },
                "observation": (
                    "The agent reaches toward the bed to pick up the book, but the book is not "
                    "there anymore. The bed, pillow, lamp, chair, and door remain visible."
                ),
            }

        return {
            "success": True,
            "result": "success",
            "message": f"Executed {action}.",
            "observation": self._observation_text(),
        }

    def _observation_text(self) -> str:
        return (
            "Room: bedroom. Visible objects: bed, pillow, book, lamp, chair, door. "
            "The book is initially on the bed near the pillow. The chair is beside the bed. "
            "The lamp is on a small bedside surface. The door is closed. "
            "Task: Find the book and place it on the chair."
        )
