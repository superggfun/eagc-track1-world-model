import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from clients.qwen_client import QwenClient, QwenClientError  # noqa: E402
from main import load_config  # noqa: E402
from perception.json_utils import parse_json_from_text  # noqa: E402


VISION_SMOKE_PROMPT = """Inspect the provided indoor scene image.
Return one valid JSON object only. Do not use markdown or explanatory text.
The JSON must include:
{
  "scene_type": "short scene type",
  "visible_objects": ["object_name"],
  "spatial_relations": [
    {"subject": "object", "relation": "on|near|beside|inside|under|at", "object": "object_or_place", "confidence": 0.0}
  ],
  "uncertain_items": [
    {"item": "object_or_relation", "reason": "short reason", "confidence": 0.0}
  ]
}
Do not invent objects unrelated to the image."""


def main() -> int:
    args = parse_args()
    image_path = _resolve_path(args.image_path)
    output_dir = PROJECT_ROOT / "outputs" / "vision_smoke"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "qwen_vision_raw.txt"
    response_path = output_dir / "qwen_vision_response.json"
    error_path = output_dir / "qwen_vision_error.json"

    if not image_path.exists():
        message = f"Image does not exist: {image_path}"
        error_path.write_text(json.dumps({"error": message}, indent=2), encoding="utf-8")
        print(message)
        return 1

    config = load_config(PROJECT_ROOT / "config.yaml")
    client = QwenClient(
        base_url=str(config["base_url"]),
        model=str(config["model"]),
        temperature=float(config["temperature"]),
        max_tokens=int(config["max_tokens"]),
        audit_path=output_dir / "qwen_calls.jsonl",
    )

    try:
        raw = client.chat_vision(image_path, VISION_SMOKE_PROMPT)
    except QwenClientError as exc:
        error_path.write_text(json.dumps({"error": str(exc)}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Vision call failed: {exc}")
        return 1

    raw_path.write_text(raw, encoding="utf-8")
    try:
        parsed = parse_json_from_text(raw)
    except (ValueError, TypeError) as exc:
        error_path.write_text(
            json.dumps({"error": f"Failed to parse JSON: {exc}"}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Failed to parse JSON. Raw response saved to {raw_path}")
        return 1

    missing = [key for key in ["scene_type", "visible_objects", "spatial_relations", "uncertain_items"] if key not in parsed]
    if missing:
        error_path.write_text(
            json.dumps({"error": "Missing required keys", "missing_keys": missing}, indent=2),
            encoding="utf-8",
        )
        print(f"Vision JSON missing required keys: {missing}")
        return 1

    response_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Vision smoke response written to {response_path}")
    print(f"Vision smoke raw output written to {raw_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test Qwen vision chat via local vLLM.")
    parser.add_argument("--image-path", required=True, help="Local image path to send as data URL.")
    return parser.parse_args()


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


if __name__ == "__main__":
    raise SystemExit(main())
