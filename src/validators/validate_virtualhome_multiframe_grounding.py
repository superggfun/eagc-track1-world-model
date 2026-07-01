from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def validate(status_path: Path) -> List[str]:
    errors: List[str] = []
    status = _read_json(status_path, errors, "multiframe_qwen_status")
    if errors:
        return errors
    output_dir = status_path.parent
    comparison = _read_json(output_dir / "episode_visual_symbolic_comparison.json", errors, "episode_visual_symbolic_comparison")
    if errors:
        return errors

    if status.get("success") is True:
        if int(status.get("successful_vision_frame_count", 0)) < 1:
            errors.append("successful_vision_frame_count must be >= 1 when multiframe status succeeds.")
        vision = _read_json(output_dir / "multiframe_qwen_vision.json", errors, "multiframe_qwen_vision")
        per_frame = vision.get("per_frame_results", [])
        if not isinstance(per_frame, list) or not per_frame:
            errors.append("multiframe_qwen_vision.per_frame_results must be non-empty when status succeeds.")
        summary = comparison.get("summary")
        if not isinstance(summary, dict) or not summary:
            errors.append("episode_visual_symbolic_comparison.summary must be non-empty when status succeeds.")
        elif "average_qwen_latency" not in summary:
            errors.append("episode_visual_symbolic_comparison.summary.average_qwen_latency is required.")
    else:
        reason = str(status.get("reason") or "").strip()
        if not reason:
            errors.append("multiframe_qwen_status.reason must be non-empty when success=false.")
    return errors


def _read_json(path: Path, errors: List[str], label: str) -> Dict[str, Any]:
    if not path.exists():
        errors.append(f"Missing {label}: {path}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid {label} JSON: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{label} must be a JSON object.")
        return {}
    return data


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m validators.validate_virtualhome_multiframe_grounding outputs/virtualhome_spike/multiframe_qwen_status.json")
        return 2
    errors = validate(Path(sys.argv[1]))
    if errors:
        print("VirtualHome multi-frame grounding validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("VirtualHome multi-frame grounding validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
