from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def validate(status_path: Path) -> List[str]:
    errors: List[str] = []
    status = _read_json(status_path, errors, "qwen_vision_status")
    if errors:
        return errors
    output_dir = status_path.parent
    if status.get("success") is True:
        extraction = _read_json(output_dir / "qwen_vision_extraction.json", errors, "qwen_vision_extraction")
        comparison = _read_json(output_dir / "visual_symbolic_comparison.json", errors, "visual_symbolic_comparison")
        if "visible_objects" not in extraction:
            errors.append("qwen_vision_extraction.visible_objects is required when Qwen vision succeeds.")
        elif not isinstance(extraction.get("visible_objects"), list):
            errors.append("qwen_vision_extraction.visible_objects must be a list.")
        summary = comparison.get("summary") if isinstance(comparison, dict) else None
        if not isinstance(summary, dict) or not summary:
            errors.append("visual_symbolic_comparison.summary is required when Qwen vision succeeds.")
    else:
        reason = str(status.get("reason") or "").strip()
        if not reason:
            errors.append("qwen_vision_status.reason must be non-empty when success=false.")
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
        print("Usage: python -m validators.validate_virtualhome_visual_symbolic_comparison outputs/virtualhome_spike/qwen_vision_status.json")
        return 2
    errors = validate(Path(sys.argv[1]))
    if errors:
        print("VirtualHome visual-symbolic comparison validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("VirtualHome visual-symbolic comparison validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
