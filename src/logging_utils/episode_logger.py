import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class EpisodeLogger:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text("", encoding="utf-8")

    def log(
        self,
        step: int,
        event_type: str,
        observation: str = "",
        model_update: Dict[str, Any] | None = None,
        action: str = "",
        result: str = "",
        notes: str = "",
    ) -> None:
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "event_type": event_type,
            "observation": observation,
            "model_update": model_update or {},
            "action": action,
            "result": result,
            "notes": notes,
        }
        with self.output_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
