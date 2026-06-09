import json
import re
from typing import Any, Dict


def extract_json_from_text(text: str) -> str:
    """Extract the first JSON object from raw model text or a markdown fence."""
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output.")
    return stripped[start : end + 1]


def parse_json_from_text(text: str) -> Dict[str, Any]:
    parsed = json.loads(extract_json_from_text(text))
    if not isinstance(parsed, dict):
        raise ValueError("Expected a top-level JSON object.")
    return parsed
