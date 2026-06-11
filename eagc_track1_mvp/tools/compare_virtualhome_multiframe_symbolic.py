from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.compare_virtualhome_visual_symbolic import (  # noqa: E402
    _match_visual_object,
    _match_visual_relation,
    _read_json,
    _symbolic_names,
)


DEFAULT_OUTPUT_DIR = Path("outputs/virtualhome_spike")


def main() -> int:
    args = parse_args()
    output_dir = _resolve_path(args.output_dir)
    comparison = compare(output_dir)
    json_path = output_dir / "episode_visual_symbolic_comparison.json"
    md_path = output_dir / "episode_visual_symbolic_comparison.md"
    json_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_to_markdown(comparison), encoding="utf-8")
    print(f"VirtualHome episode visual-symbolic comparison written to {json_path}")
    print(f"VirtualHome episode visual-symbolic comparison written to {md_path}")
    return 0


def compare(output_dir: Path) -> Dict[str, Any]:
    status = _read_json(output_dir / "multiframe_qwen_status.json")
    if status.get("success") is not True:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": False,
            "reason": status.get("reason", "multiframe_qwen_not_available"),
            "summary": {},
            "per_frame_summary": [],
            "confidence_notes": ["Multi-frame Qwen vision was unavailable; symbolic pipeline remains valid."],
        }

    multiframe = _read_json(output_dir / "multiframe_qwen_vision.json")
    scene_graph = _read_json(output_dir / "scene_graph.json")
    world_model = _read_json(output_dir / "converted_world_model.json")
    program_log = _read_json(output_dir / "program_log.json")
    frame_status = _read_json(output_dir / "task_frame_export_status.json")
    symbolic_names = _symbolic_names(scene_graph, world_model)

    per_frame_summary: List[Dict[str, Any]] = []
    all_object_matches: List[Dict[str, Any]] = []
    all_relation_matches: List[Dict[str, Any]] = []
    action_evidence_count = 0
    unique_visible_objects: set[str] = set()
    for row in multiframe.get("per_frame_results", []):
        if not isinstance(row, dict) or row.get("success") is not True:
            per_frame_summary.append(
                {
                    "frame_index": row.get("frame_index") if isinstance(row, dict) else None,
                    "success": False,
                    "reason": row.get("reason", "") if isinstance(row, dict) else "invalid_frame_result",
                }
            )
            continue
        extraction = row.get("extraction", {})
        visible_objects = extraction.get("visible_objects", []) if isinstance(extraction, dict) else []
        visible_relations = extraction.get("visible_relations", []) if isinstance(extraction, dict) else []
        object_matches = [_match_visual_object(item, symbolic_names) for item in visible_objects]
        relation_matches = [_match_visual_relation(item, world_model) for item in visible_relations]
        action_evidence = extraction.get("action_evidence", []) if isinstance(extraction, dict) else []
        action_evidence_count += len(action_evidence) if isinstance(action_evidence, list) else 0
        for item in object_matches:
            if item.get("normalized"):
                unique_visible_objects.add(str(item["normalized"]))
        all_object_matches.extend(object_matches)
        all_relation_matches.extend(relation_matches)
        per_frame_summary.append(
            {
                "frame_index": row.get("frame_index"),
                "frame_path": row.get("frame_path", ""),
                "success": True,
                "visible_object_count": len(visible_objects),
                "matched_object_count": len([item for item in object_matches if item["status"] == "supported_by_scene_graph"]),
                "unmatched_visual_object_count": len([item for item in object_matches if item["status"] == "not_found_in_scene_graph"]),
                "visible_relation_count": len(visible_relations),
                "matched_relation_count": len([item for item in relation_matches if item["status"] == "supported_by_scene_graph"]),
                "action_evidence_count": len(action_evidence) if isinstance(action_evidence, list) else 0,
                "latency_seconds": row.get("latency_seconds", 0.0),
            }
        )

    matched_objects = [item for item in all_object_matches if item["status"] == "supported_by_scene_graph"]
    unmatched_objects = [item for item in all_object_matches if item["status"] == "not_found_in_scene_graph"]
    matched_relations = [item for item in all_relation_matches if item["status"] == "supported_by_scene_graph"]
    tasks = program_log.get("tasks", []) if isinstance(program_log.get("tasks"), list) else []
    successful_tasks = [task for task in tasks if isinstance(task, dict) and task.get("status") == "success"]
    latencies = [float(row.get("latency_seconds", 0.0)) for row in multiframe.get("per_frame_results", []) if isinstance(row, dict) and row.get("success")]
    comparison = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "reason": "episode_visual_symbolic_comparison_completed",
        "task_frame_export_success": frame_status.get("success") is True,
        "task_count": len(tasks),
        "successful_task_count": len(successful_tasks),
        "per_frame_summary": per_frame_summary,
        "visual_warnings": [
            {"object": item["visual_object"], "reason": "not_found_in_scene_graph"}
            for item in unmatched_objects[:20]
        ],
        "not_visible_symbolic_object_count": max(0, len(symbolic_names) - len(unique_visible_objects)),
        "summary": {
            "frame_count": int(status.get("frame_count", 0)),
            "successful_vision_frame_count": int(status.get("successful_vision_frame_count", 0)),
            "total_visible_object_mentions": len(all_object_matches),
            "unique_visible_objects": sorted(unique_visible_objects),
            "matched_object_count": len(matched_objects),
            "unmatched_visual_object_count": len(unmatched_objects),
            "action_evidence_count": action_evidence_count,
            "relation_match_count": len(matched_relations),
            "average_qwen_latency": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        },
        "limitations": [
            "Multi-frame observations still cover only selected task frames, not the full scene graph.",
            "Scene graph objects not visible in selected frames are not Qwen failures.",
            "Unmatched or hallucinated visual objects are warnings.",
            "No training, fine-tuning, or official EAGC hidden evaluation is performed.",
        ],
    }
    return comparison


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare multi-frame Qwen vision with VirtualHome symbolic state.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def _to_markdown(comparison: Dict[str, Any]) -> str:
    summary = comparison.get("summary", {})
    lines = [
        "# VirtualHome Episode Visual-Symbolic Comparison",
        "",
        f"- success: `{comparison.get('success')}`",
        f"- reason: `{comparison.get('reason')}`",
        f"- frame_count: `{summary.get('frame_count', 0)}`",
        f"- successful_vision_frame_count: `{summary.get('successful_vision_frame_count', 0)}`",
        f"- total_visible_object_mentions: `{summary.get('total_visible_object_mentions', 0)}`",
        f"- unique_visible_objects: `{len(summary.get('unique_visible_objects', []))}`",
        f"- matched_object_count: `{summary.get('matched_object_count', 0)}`",
        f"- unmatched_visual_object_count: `{summary.get('unmatched_visual_object_count', 0)}`",
        f"- action_evidence_count: `{summary.get('action_evidence_count', 0)}`",
        f"- relation_match_count: `{summary.get('relation_match_count', 0)}`",
        f"- average_qwen_latency: `{summary.get('average_qwen_latency', 0.0)}`",
        "",
        "## Per Frame",
        "",
        "| frame | success | visible objects | matched objects | relation matches | action evidence | latency |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in comparison.get("per_frame_summary", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {row.get('frame_index')} | {row.get('success')} | {row.get('visible_object_count', 0)} | "
            f"{row.get('matched_object_count', 0)} | {row.get('matched_relation_count', 0)} | "
            f"{row.get('action_evidence_count', 0)} | {row.get('latency_seconds', 0.0)} |"
        )
    lines.extend(["", "## Limitations", ""])
    for item in comparison.get("limitations", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


if __name__ == "__main__":
    raise SystemExit(main())
