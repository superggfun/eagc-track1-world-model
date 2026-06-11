from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image


DEFAULT_OUTPUT_DIR = Path("outputs/virtualhome_spike")


def main() -> int:
    output_dir = DEFAULT_OUTPUT_DIR
    report = build_report(output_dir)
    json_path = output_dir / "visual_symbolic_evidence_report.json"
    md_path = output_dir / "visual_symbolic_evidence_report.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_to_markdown(report), encoding="utf-8")
    print(f"VirtualHome visual-symbolic evidence report written to {json_path}")
    print(f"VirtualHome visual-symbolic evidence report written to {md_path}")
    return 0


def build_report(output_dir: Path) -> Dict[str, Any]:
    scene_graph = _read_json(output_dir / "scene_graph.json")
    program_log = _read_json(output_dir / "program_log.json")
    world_model = _read_json(output_dir / "converted_world_model.json")
    episode_log_rows = _read_jsonl(output_dir / "converted_episode_log.jsonl")
    comparison = _read_json(output_dir / "visual_symbolic_comparison.json")
    qwen_status = _read_json(output_dir / "qwen_vision_status.json")
    frame_path = output_dir / "frame_000.png"
    frame_status = _read_json(output_dir / "frame_export_status.json")
    frame_info = _frame_info(frame_path)
    tasks = program_log.get("tasks", []) if isinstance(program_log, dict) else []
    successful_tasks = [task for task in tasks if isinstance(task, dict) and task.get("status") == "success"]
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scene_graph_object_count": _count_list(scene_graph.get("nodes") if isinstance(scene_graph, dict) else None),
        "scene_graph_relation_count": _count_list(scene_graph.get("edges") if isinstance(scene_graph, dict) else None),
        "converted_world_model_object_count": _count_list(world_model.get("objects") if isinstance(world_model, dict) else None),
        "converted_world_model_relation_count": _count_list(world_model.get("relations") if isinstance(world_model, dict) else None),
        "episode_log_event_count": len(episode_log_rows),
        "executed_task_count": len(tasks),
        "successful_task_count": len(successful_tasks),
        "frame_available": frame_info["available"],
        "frame_path": str(frame_path) if frame_info["available"] else "",
        "frame_dimensions": frame_info.get("dimensions"),
        "qwen_vision_available": qwen_status.get("success") is True,
        "qwen_visible_object_count": _summary_value(comparison, "visible_object_count"),
        "qwen_matched_object_count": _summary_value(comparison, "matched_object_count"),
        "qwen_unmatched_visual_object_count": _summary_value(comparison, "unmatched_visual_object_count"),
        "visual_symbolic_comparison_path": str(output_dir / "visual_symbolic_comparison.json")
        if comparison
        else "",
        "frame_export_status": {
            "success": frame_status.get("success") if isinstance(frame_status, dict) else None,
            "reason": frame_status.get("reason", "") if isinstance(frame_status, dict) else "",
            "camera_index": frame_status.get("camera_index") if isinstance(frame_status, dict) else None,
        },
        "symbolic_evidence": {
            "scene_graph_path": str(output_dir / "scene_graph.json"),
            "program_log_path": str(output_dir / "program_log.json"),
            "converted_world_model_path": str(output_dir / "converted_world_model.json"),
            "converted_episode_log_path": str(output_dir / "converted_episode_log.jsonl"),
        },
        "visual_evidence": {
            "frame_path": str(frame_path) if frame_info["available"] else "",
            "frame_available": frame_info["available"],
        },
        "limitations": [
            "Scene graph is symbolic simulator state.",
            "Frame export is only a visual observation if available.",
            "Qwen vision comparison, when available, uses a single-frame visual observation.",
            "No video or multi-view visual comparison is performed yet.",
            "No training or fine-tuning is performed.",
            "No official EAGC runtime validation is performed in this version.",
        ],
    }
    return report


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _summary_value(comparison: Dict[str, Any], key: str) -> int:
    summary = comparison.get("summary", {}) if isinstance(comparison, dict) else {}
    value = summary.get(key, 0) if isinstance(summary, dict) else 0
    return int(value) if isinstance(value, (int, float)) else 0


def _frame_info(path: Path) -> Dict[str, Any]:
    if not path.exists() or path.stat().st_size <= 0:
        return {"available": False}
    try:
        with Image.open(path) as image:
            return {"available": True, "dimensions": {"width": image.size[0], "height": image.size[1]}}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def _to_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# VirtualHome Visual-Symbolic Evidence Report",
        "",
        f"- generated_at: `{report['timestamp']}`",
        f"- scene_graph_object_count: `{report['scene_graph_object_count']}`",
        f"- scene_graph_relation_count: `{report['scene_graph_relation_count']}`",
        f"- converted_world_model_object_count: `{report['converted_world_model_object_count']}`",
        f"- converted_world_model_relation_count: `{report['converted_world_model_relation_count']}`",
        f"- executed_task_count: `{report['executed_task_count']}`",
        f"- successful_task_count: `{report['successful_task_count']}`",
        f"- frame_available: `{report['frame_available']}`",
        f"- qwen_vision_available: `{report['qwen_vision_available']}`",
        f"- qwen_visible_object_count: `{report['qwen_visible_object_count']}`",
        f"- qwen_matched_object_count: `{report['qwen_matched_object_count']}`",
        f"- qwen_unmatched_visual_object_count: `{report['qwen_unmatched_visual_object_count']}`",
    ]
    if report.get("frame_dimensions"):
        dimensions = report["frame_dimensions"]
        lines.append(f"- frame_dimensions: `{dimensions['width']}x{dimensions['height']}`")
    frame_status = report.get("frame_export_status", {})
    lines.extend(
        [
            f"- frame_export_success: `{frame_status.get('success')}`",
            f"- frame_export_reason: `{frame_status.get('reason')}`",
            "",
            "## Limitations",
            "",
        ]
    )
    for item in report.get("limitations", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
