from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clients.qwen_client import QwenClient, QwenClientError  # noqa: E402
from main import load_config  # noqa: E402
from perception.json_utils import parse_json_from_text  # noqa: E402


DEFAULT_OUTPUT_DIR = Path("outputs/virtualhome_spike")
REQUIRED_KEYS = [
    "visible_objects",
    "visible_relations",
    "likely_room_type",
    "action_evidence",
    "uncertainty",
    "short_description",
]


PROMPT = """Inspect this single frame from a VirtualHome household activity episode.
Return one valid JSON object only. Do not use markdown or explanatory text.
The JSON object must contain exactly these top-level fields:
{
  "visible_objects": ["object_name"],
  "visible_relations": [
    {"subject": "object", "relation": "on|near|beside|inside|under|at|held_by|open", "object": "object_or_surface", "confidence": 0.0}
  ],
  "likely_room_type": "living_room|kitchen|bedroom|bathroom|office|unknown",
  "action_evidence": [
    {"action_or_state": "short phrase", "evidence": "visible cue", "confidence": 0.0}
  ],
  "uncertainty": [
    {"item": "object_or_action", "reason": "why uncertain", "confidence": 0.0}
  ],
  "short_description": "one short sentence"
}
Use only what is visible in the frame. Do not infer the full simulator scene graph."""


def main() -> int:
    args = parse_args()
    output_dir = _resolve_path(args.output_dir)
    frame_dir = _resolve_path(args.frame_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    status_path = output_dir / "multiframe_qwen_status.json"
    result_path = output_dir / "multiframe_qwen_vision.json"
    raw_path = output_dir / "multiframe_qwen_raw_responses.json"
    frame_paths = sorted(frame_dir.glob("*.png"))[: max(1, args.max_frames)]
    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": False,
        "reason": "",
        "frame_dir": str(frame_dir),
        "frame_count": len(frame_paths),
        "successful_vision_frame_count": 0,
        "failed_vision_frame_count": 0,
        "average_qwen_latency": 0.0,
        "qwen_call_count": 0,
        "qwen_call_success_count": 0,
        "qwen_call_failure_count": 0,
    }
    if not frame_paths:
        status["reason"] = "virtualhome_task_frames_missing"
        _write_json(status_path, status)
        print("No task frames found; run targeted-virtualhome-multiframe or --export-task-frames first.")
        return 0

    config = load_config(PROJECT_ROOT / "config.yaml")
    client = QwenClient(
        base_url=str(config["base_url"]),
        model=str(config["model"]),
        temperature=float(config.get("temperature", 0.2)),
        max_tokens=min(int(config.get("max_tokens", 2048)), 1024),
        timeout_seconds=int(args.timeout_seconds),
        audit_path=output_dir / "multiframe_qwen_calls.jsonl",
    )

    per_frame_results: List[Dict[str, Any]] = []
    raw_responses: List[Dict[str, Any]] = []
    for index, frame_path in enumerate(frame_paths):
        row, raw_row = _process_frame(client, frame_path, index)
        per_frame_results.append(row)
        raw_responses.append(raw_row)

    successes = [row for row in per_frame_results if row.get("success")]
    latencies = [float(row.get("latency_seconds", 0.0)) for row in successes]
    status.update(
        {
            "success": bool(successes),
            "reason": "multiframe_qwen_vision_completed" if successes else "all_multiframe_qwen_vision_failed",
            "successful_vision_frame_count": len(successes),
            "failed_vision_frame_count": len(per_frame_results) - len(successes),
            "average_qwen_latency": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
            "qwen_call_count": client.call_count,
            "qwen_call_success_count": client.success_count,
            "qwen_call_failure_count": client.failure_count,
        }
    )
    _write_json(
        result_path,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "frame_count": len(per_frame_results),
            "successful_vision_frame_count": len(successes),
            "per_frame_results": per_frame_results,
        },
    )
    _write_json(raw_path, {"timestamp": datetime.now(timezone.utc).isoformat(), "responses": raw_responses})
    _write_json(status_path, status)
    print(f"VirtualHome multi-frame Qwen vision written to {result_path}")
    print(f"VirtualHome multi-frame Qwen status written to {status_path}")
    return 0


def _process_frame(client: QwenClient, frame_path: Path, index: int) -> tuple[Dict[str, Any], Dict[str, Any]]:
    started = time.perf_counter()
    row: Dict[str, Any] = {
        "frame_index": index,
        "frame_path": str(frame_path),
        "success": False,
        "reason": "",
        "latency_seconds": 0.0,
        "extraction": {},
    }
    if not _frame_readable(frame_path, row):
        return row, {"frame_index": index, "frame_path": str(frame_path), "raw_text": ""}
    raw_text = ""
    try:
        raw_text = client.chat_vision(frame_path, PROMPT, temperature=0.1, max_tokens=1024)
        parsed = parse_json_from_text(raw_text)
        extraction = _normalize_extraction(parsed)
        row.update(
            {
                "success": True,
                "reason": "frame_qwen_vision_completed",
                "extraction": extraction,
            }
        )
    except QwenClientError as exc:
        row.update({"reason": _classify_qwen_error(str(exc)), "error_type": type(exc).__name__, "error_message": str(exc)})
    except (ValueError, TypeError) as exc:
        row.update({"reason": "qwen_vision_parse_failed", "error_type": type(exc).__name__, "error_message": str(exc)})
    finally:
        row["latency_seconds"] = round(time.perf_counter() - started, 3)
    return row, {"frame_index": index, "frame_path": str(frame_path), "raw_text": raw_text, "raw_chars": len(raw_text)}


def _frame_readable(frame_path: Path, row: Dict[str, Any]) -> bool:
    if not frame_path.exists():
        row["reason"] = "frame_missing"
        return False
    try:
        with Image.open(frame_path) as image:
            row["frame_width"], row["frame_height"] = image.size
            image.verify()
        return True
    except Exception as exc:
        row.update({"reason": "frame_unreadable", "error_type": type(exc).__name__, "error_message": str(exc)})
        return False


def _normalize_extraction(parsed: Any) -> Dict[str, Any]:
    data = dict(parsed) if isinstance(parsed, dict) else {}
    normalized = {key: data.get(key) for key in REQUIRED_KEYS}
    for key in ["visible_objects", "visible_relations", "action_evidence", "uncertainty"]:
        if not isinstance(normalized.get(key), list):
            normalized[key] = []
    normalized["likely_room_type"] = str(normalized.get("likely_room_type") or "unknown")
    normalized["short_description"] = str(normalized.get("short_description") or "")
    return normalized


def _classify_qwen_error(message: str) -> str:
    lowered = message.lower()
    if "timed out" in lowered or "timeout" in lowered:
        return "qwen_vision_timeout"
    if "connection" in lowered or "refused" in lowered:
        return "qwen_endpoint_unavailable"
    return "qwen_vision_call_failed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Qwen vision over VirtualHome task frames.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--frame-dir", default=str(DEFAULT_OUTPUT_DIR / "task_frames"))
    parser.add_argument("--max-frames", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    return parser.parse_args()


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
