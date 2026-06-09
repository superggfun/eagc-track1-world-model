from typing import Any, Dict

from clients.qwen_client import QwenClient
from perception.prompts import EXTRACTOR_SYSTEM_PROMPT, build_extraction_prompt


class VLMExtractor:
    """Text-only extractor. Image inputs can be added behind this interface later."""

    def __init__(self, client: QwenClient) -> None:
        self.client = client

    def extract(self, observation: str, task: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT},
            {"role": "user", "content": build_extraction_prompt(observation, task)},
        ]
        raw_update = self.client.chat_json(messages)
        return normalize_extraction(raw_update)


def normalize_extraction(update: Dict[str, Any]) -> Dict[str, Any]:
    defaults = {
        "rooms": [],
        "objects": [],
        "relations": [],
        "states": [],
        "affordances": [],
        "uncertainty": [],
    }
    normalized = {**defaults, **{k: v for k, v in update.items() if k in defaults}}
    for key in defaults:
        if not isinstance(normalized[key], list):
            normalized[key] = []
    return normalized
