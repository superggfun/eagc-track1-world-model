import json
from pathlib import Path
from typing import Any, Dict

from world_model.schema import new_world_model
from world_model.update import apply_extraction


class WorldModelStore:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.world_model: Dict[str, Any] = {}

    def initialize(self, episode_id: str) -> Dict[str, Any]:
        self.world_model = new_world_model(episode_id)
        return self.world_model

    def update_from_extraction(self, extraction: Dict[str, Any]) -> Dict[str, Any]:
        self.world_model = apply_extraction(self.world_model, extraction)
        return self.world_model

    def add_plan(self, plan: Dict[str, Any]) -> None:
        self.world_model.setdefault("plans", []).append(plan)

    def add_exception(self, exception: Dict[str, Any]) -> None:
        self.world_model.setdefault("exceptions", []).append(exception)

    def save(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            json.dumps(self.world_model, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
