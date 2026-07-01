from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clients.qwen_client import QwenClient, QwenClientError  # noqa: E402
from main import load_config  # noqa: E402
from perception.json_utils import parse_json_from_text  # noqa: E402


DEFAULT_OUTPUT_DIR = Path("outputs/virtualhome_spike")
REQUIRED_KEYS = [
    "visible_objects",
    "likely_room_type",
    "visible_surfaces",
    "visible_relations",
    "uncertain_objects",
    "short_description",
]


PROMPT = """Inspect this single VirtualHome simulator frame.
Return one valid JSON object only. Do not use markdown or explanatory text.
The JSON object must contain exactly these top-level fields:
{
  "visible_objects": ["object_name"],
  "likely_room_type": "living_room|kitchen|bedroom|bathroom|unknown",
  "visible_surfaces": ["surface_or_furniture_name"],
  "visible_relations": [
    {"subject": "object", "relation": "on|near|beside|inside|under|at", "object": "object_or_surface", "confidence": 0.0}
  ],
  "uncertain_objects": [
    {"name": "object_or_region", "reason": "why uncertain", "confidence": 0.0}
  ],
  "short_description": "one short sentence"
}
Use only what is visible in the frame. Do not infer the full simulator scene graph.
If an item is ambiguous, put it in uncertain_objects rather than inventing details."""


def main() -> int:
    args = parse_args()
    output_dir = _resolve_path(args.output_dir)
    frame_path = _resolve_path(args.frame_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    status_path = output_dir / "qwen_vision_status.json"
    extraction_path = output_dir / "qwen_vision_extraction.json"
    raw_path = output_dir / "qwen_vision_raw_response.json"
    status = _base_status(frame_path)

    if not _validate_frame(frame_path, status):
        _write_json(status_path, status)
        print(f"VirtualHome Qwen vision status written to {status_path}")
        return 0

    config = load_config(PROJECT_ROOT / "config.yaml")
    client = QwenClient(
        base_url=str(config["base_url"]),
        model=str(config["model"]),
        temperature=float(config.get("temperature", 0.2)),
        max_tokens=min(int(config.get("max_tokens", 2048)), 1024),
        timeout_seconds=int(args.timeout_seconds),
        audit_path=output_dir / "qwen_vision_calls.jsonl",
    )

    started = time.perf_counter()
    raw_text = ""
    try:
        raw_text = client.chat_vision(frame_path, PROMPT, temperature=0.1, max_tokens=1024)
        _write_json(
            raw_path,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "raw_text": raw_text,
                "raw_chars": len(raw_text),
            },
        )
        parsed = parse_json_from_text(raw_text)
    except QwenClientError as exc:
        status.update(
            {
                "reason": _classify_qwen_error(str(exc)),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
        if raw_text:
            _write_json(raw_path, {"raw_text": raw_text, "raw_chars": len(raw_text)})
        _write_json(status_path, _finish_status(status, client, started))
        print(f"Qwen vision call failed gracefully: {status['reason']}")
        return 0
    except (ValueError, TypeError) as exc:
        status.update(
            {
                "reason": "qwen_vision_parse_failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
        if raw_text:
            _write_json(raw_path, {"raw_text": raw_text, "raw_chars": len(raw_text)})
        _write_json(status_path, _finish_status(status, client, started))
        print(f"Qwen vision parse failed gracefully: {exc}")
        return 0
    except TimeoutError as exc:
        status.update(
            {
                "reason": "qwen_vision_timeout",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
        _write_json(status_path, _finish_status(status, client, started))
        print(f"Qwen vision timed out gracefully: {exc}")
        return 0

    normalized = _normalize_extraction(parsed)
    missing = [key for key in REQUIRED_KEYS if key not in normalized]
    if missing:
        status.update(
            {
                "reason": "qwen_vision_parse_failed",
                "error_type": "MissingRequiredKeys",
                "error_message": f"Missing required keys: {missing}",
                "missing_keys": missing,
            }
        )
        _write_json(status_path, _finish_status(status, client, started))
        return 0

    _write_json(extraction_path, normalized)
    status.update(
        {
            "success": True,
            "reason": "qwen_vision_extraction_completed",
            "extraction_path": str(extraction_path),
            "raw_response_path": str(raw_path),
            "visible_object_count": len(normalized.get("visible_objects", [])),
            "visible_relation_count": len(normalized.get("visible_relations", [])),
        }
    )
    _write_json(status_path, _finish_status(status, client, started))
    print(f"VirtualHome Qwen vision extraction written to {extraction_path}")
    print(f"VirtualHome Qwen vision status written to {status_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Qwen vision extraction on a VirtualHome exported frame.")
    parser.add_argument("--frame-path", default=str(DEFAULT_OUTPUT_DIR / "frame_000.png"))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--timeout-seconds", type=int, default=120)
    return parser.parse_args()


def _base_status(frame_path: Path) -> Dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": False,
        "reason": "",
        "error_type": "",
        "error_message": "",
        "frame_path": str(frame_path),
        "frame_exists": frame_path.exists(),
        "frame_readable": False,
        "frame_width": None,
        "frame_height": None,
        "qwen_call_count": 0,
        "qwen_call_success_count": 0,
        "qwen_call_failure_count": 0,
        "latency_seconds": 0.0,
    }


def _validate_frame(frame_path: Path, status: Dict[str, Any]) -> bool:
    if not frame_path.exists():
        status["reason"] = "virtualhome_frame_missing"
        status["error_message"] = f"Frame does not exist: {frame_path}"
        return False
    try:
        with Image.open(frame_path) as image:
            status["frame_width"], status["frame_height"] = image.size
            image.verify()
        status["frame_readable"] = True
        return True
    except Exception as exc:
        status["reason"] = "virtualhome_frame_unreadable"
        status["error_type"] = type(exc).__name__
        status["error_message"] = str(exc)
        return False


def _normalize_extraction(parsed: Any) -> Dict[str, Any]:
    data = dict(parsed) if isinstance(parsed, dict) else {}
    normalized = {key: data.get(key) for key in REQUIRED_KEYS}
    for key in ["visible_objects", "visible_surfaces", "visible_relations", "uncertain_objects"]:
        if not isinstance(normalized.get(key), list):
            normalized[key] = []
    normalized["likely_room_type"] = str(normalized.get("likely_room_type") or "unknown")
    normalized["short_description"] = str(normalized.get("short_description") or "")
    return normalized


def _classify_qwen_error(message: str) -> str:
    lowered = message.lower()
    if "timed out" in lowered or "timeout" in lowered:
        return "qwen_vision_timeout"
    if "connection" in lowered or "refused" in lowered or "models" in lowered:
        return "qwen_endpoint_unavailable"
    return "qwen_vision_call_failed"


def _finish_status(status: Dict[str, Any], client: QwenClient, started: float) -> Dict[str, Any]:
    status.update(
        {
            "latency_seconds": round(time.perf_counter() - started, 3),
            "qwen_call_count": client.call_count,
            "qwen_call_success_count": client.success_count,
            "qwen_call_failure_count": client.failure_count,
        }
    )
    return status


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


if __name__ == "__main__":
    raise SystemExit(main())
