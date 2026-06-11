from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image


def validate(status_path: Path) -> List[str]:
    errors: List[str] = []
    if not status_path.exists():
        return [f"Missing frame export status: {status_path}"]
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"Invalid frame export status JSON: {exc}"]
    if not isinstance(status, dict):
        return ["frame_export_status.json must contain a JSON object."]

    if status.get("success") is True:
        _validate_success(status, status_path, errors)
    else:
        reason = str(status.get("reason") or "").strip()
        if not reason:
            errors.append("Frame export failure status must include a non-empty reason.")
    return errors


def _validate_success(status: Dict[str, Any], status_path: Path, errors: List[str]) -> None:
    frame_path_text = str(status.get("frame_path") or "").strip()
    if not frame_path_text:
        errors.append("Successful frame export must include frame_path.")
        return
    frame_path = Path(frame_path_text)
    if not frame_path.is_absolute():
        cwd_relative = Path.cwd() / frame_path
        frame_path = cwd_relative if cwd_relative.exists() else status_path.parent / frame_path
    if not frame_path.exists():
        errors.append(f"Frame file does not exist: {frame_path}")
        return
    if frame_path.stat().st_size <= 0:
        errors.append(f"Frame file is empty: {frame_path}")
        return
    try:
        with Image.open(frame_path) as image:
            width, height = image.size
            image.verify()
    except Exception as exc:
        errors.append(f"Frame file is not a readable image: {type(exc).__name__}: {exc}")
        return
    if width < 64 or height < 64:
        errors.append(f"Frame dimensions are unexpectedly small: {width}x{height}")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m validators.validate_virtualhome_frame_export outputs/virtualhome_spike/frame_export_status.json")
        return 2
    errors = validate(Path(sys.argv[1]))
    if errors:
        print("VirtualHome frame export validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("VirtualHome frame export validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
