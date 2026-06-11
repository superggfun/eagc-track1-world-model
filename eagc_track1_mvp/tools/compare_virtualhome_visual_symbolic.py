from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("outputs/virtualhome_spike")


def main() -> int:
    args = parse_args()
    output_dir = _resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison = compare(output_dir)
    json_path = output_dir / "visual_symbolic_comparison.json"
    md_path = output_dir / "visual_symbolic_comparison.md"
    json_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_to_markdown(comparison), encoding="utf-8")
    print(f"VirtualHome visual-symbolic comparison written to {json_path}")
    print(f"VirtualHome visual-symbolic comparison written to {md_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare VirtualHome Qwen visual extraction with symbolic scene graph.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def compare(output_dir: Path) -> Dict[str, Any]:
    qwen_status = _read_json(output_dir / "qwen_vision_status.json")
    if qwen_status.get("success") is not True:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": False,
            "reason": qwen_status.get("reason", "qwen_vision_not_available"),
            "qwen_vision_available": False,
            "summary": {},
            "object_matches": [],
            "relation_matches": [],
            "confidence_notes": ["Qwen vision extraction was unavailable; symbolic pipeline remains valid."],
        }

    qwen = _read_json(output_dir / "qwen_vision_extraction.json")
    scene_graph = _read_json(output_dir / "scene_graph.json")
    world_model = _read_json(output_dir / "converted_world_model.json")
    program_log = _read_json(output_dir / "program_log.json")
    frame_status = _read_json(output_dir / "frame_export_status.json")

    symbolic_names = _symbolic_names(scene_graph, world_model)
    object_matches = [_match_visual_object(item, symbolic_names) for item in qwen.get("visible_objects", [])]
    relation_matches = [_match_visual_relation(item, world_model) for item in qwen.get("visible_relations", [])]
    room_support = _room_support(str(qwen.get("likely_room_type") or "unknown"), scene_graph, world_model)

    matched = [item for item in object_matches if item["status"] == "supported_by_scene_graph"]
    unmatched = [item for item in object_matches if item["status"] == "not_found_in_scene_graph"]
    relation_supported = [item for item in relation_matches if item["status"] == "supported_by_scene_graph"]
    notes = _confidence_notes(qwen, object_matches, relation_matches, room_support, frame_status)
    comparison = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "reason": "visual_symbolic_comparison_completed",
        "qwen_vision_available": True,
        "frame_available": frame_status.get("success") is True,
        "frame_path": frame_status.get("frame_path", ""),
        "likely_room_type": qwen.get("likely_room_type", "unknown"),
        "likely_room_support": room_support,
        "object_matches": object_matches,
        "relation_matches": relation_matches,
        "scene_graph_only_not_visible_count": max(0, len(symbolic_names) - len(matched)),
        "program_task_count": len(program_log.get("tasks", [])) if isinstance(program_log.get("tasks"), list) else 0,
        "summary": {
            "visible_object_count": len(qwen.get("visible_objects", [])),
            "matched_object_count": len(matched),
            "unmatched_visual_object_count": len(unmatched),
            "symbolic_object_count": len(symbolic_names),
            "relation_match_count": len(relation_supported),
            "confidence_notes": notes,
        },
        "confidence_notes": notes,
        "limitations": [
            "Single-frame visual observation should not cover the full 440-object symbolic scene graph.",
            "Scene graph objects not visible in the frame are not Qwen failures.",
            "Qwen missed small objects are not hard failures in this smoke test.",
            "Hallucinated visual objects are warnings, not a failure of the VirtualHome symbolic pipeline.",
            "No training, fine-tuning, or official EAGC runtime validation is performed.",
        ],
    }
    return comparison


def _match_visual_object(item: Any, symbolic_names: Dict[str, str]) -> Dict[str, Any]:
    name = _object_name(item)
    normalized = _normalize_name(name)
    matched_key, matched_name = _best_match(normalized, symbolic_names)
    if matched_key:
        status = "supported_by_scene_graph"
    elif not normalized:
        status = "uncertain_or_ambiguous"
    else:
        status = "not_found_in_scene_graph"
    return {
        "visual_object": name,
        "normalized": normalized,
        "status": status,
        "matched_symbolic_name": matched_name,
    }


def _match_visual_relation(item: Any, world_model: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {"visual_relation": item, "status": "uncertain_or_ambiguous", "matched_symbolic_relation": None}
    subject = _normalize_name(str(item.get("subject", "")))
    relation = _normalize_relation(str(item.get("relation", "")))
    target = _normalize_name(str(item.get("object", "")))
    candidates = []
    for rel in world_model.get("relations", []):
        if not isinstance(rel, dict):
            continue
        symbolic_subject = _normalize_name(str(rel.get("subject", "")))
        symbolic_relation = _normalize_relation(str(rel.get("relation", "")))
        symbolic_target = _normalize_name(str(rel.get("object", "")))
        subject_ok = _names_close(subject, symbolic_subject)
        target_ok = _names_close(target, symbolic_target)
        relation_ok = relation == symbolic_relation or not relation
        if subject_ok and target_ok and relation_ok:
            candidates.append(rel)
    return {
        "visual_relation": item,
        "status": "supported_by_scene_graph" if candidates else "uncertain_or_ambiguous",
        "matched_symbolic_relation": candidates[0] if candidates else None,
    }


def _room_support(room_type: str, scene_graph: Dict[str, Any], world_model: Dict[str, Any]) -> Dict[str, Any]:
    normalized_room = _normalize_name(room_type)
    if not normalized_room or normalized_room == "unknown":
        return {"status": "uncertain_or_ambiguous", "matched_room": ""}
    names = _room_names(scene_graph, world_model)
    matched_key, matched_name = _best_match(normalized_room, names)
    return {
        "status": "supported_by_scene_graph" if matched_key else "uncertain_or_ambiguous",
        "matched_room": matched_name,
    }


def _symbolic_names(scene_graph: Dict[str, Any], world_model: Dict[str, Any]) -> Dict[str, str]:
    names: Dict[str, str] = {}
    for node in scene_graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        class_name = str(node.get("class_name") or "")
        if class_name:
            names.setdefault(_normalize_name(class_name), class_name)
    for obj in world_model.get("objects", []):
        if not isinstance(obj, dict):
            continue
        name = str(obj.get("name") or obj.get("id") or "")
        if name:
            names.setdefault(_normalize_name(name), name)
    return {key: value for key, value in names.items() if key}


def _room_names(scene_graph: Dict[str, Any], world_model: Dict[str, Any]) -> Dict[str, str]:
    names: Dict[str, str] = {}
    for node in scene_graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        if str(node.get("category", "")).lower() == "rooms":
            name = str(node.get("class_name") or "")
            names.setdefault(_normalize_name(name), name)
    for room in world_model.get("rooms", []):
        if isinstance(room, str):
            names.setdefault(_normalize_name(room), room)
        elif isinstance(room, dict):
            name = str(room.get("name") or room.get("id") or "")
            names.setdefault(_normalize_name(name), name)
    return {key: value for key, value in names.items() if key}


def _best_match(normalized: str, candidates: Dict[str, str]) -> Tuple[str, str]:
    if not normalized:
        return "", ""
    aliases = _aliases(normalized)
    for alias in aliases:
        if alias in candidates:
            return alias, candidates[alias]
    for candidate, display in candidates.items():
        if any(_names_close(alias, candidate) for alias in aliases):
            return candidate, display
    return "", ""


def _names_close(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if left.rstrip("s") == right.rstrip("s"):
        return True
    return left in right or right in left


def _aliases(value: str) -> List[str]:
    aliases = [value, value.rstrip("s")]
    replacements = {
        "coffee_table": "coffeetable",
        "couch": "sofa",
        "television": "tv",
        "refrigerator": "fridge",
    }
    if value in replacements:
        aliases.append(replacements[value])
    inverse = {target: source for source, target in replacements.items()}
    if value in inverse:
        aliases.append(inverse[value])
    return list(dict.fromkeys(alias for alias in aliases if alias))


def _object_name(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("name") or item.get("object") or item.get("label") or "")
    return str(item)


def _normalize_name(value: str) -> str:
    text = value.lower().replace("-", "_").replace(" ", "_")
    text = re.sub(r"[^a-z0-9_]+", "", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def _normalize_relation(value: str) -> str:
    return _normalize_name(value)


def _confidence_notes(
    qwen: Dict[str, Any],
    object_matches: List[Dict[str, Any]],
    relation_matches: List[Dict[str, Any]],
    room_support: Dict[str, Any],
    frame_status: Dict[str, Any],
) -> List[str]:
    notes: List[str] = []
    if frame_status.get("success") is True:
        notes.append("VirtualHome frame export succeeded, so visual evidence is based on a real simulator frame.")
    if room_support.get("status") != "supported_by_scene_graph":
        notes.append("Qwen likely_room_type is not directly supported by symbolic room metadata.")
    unmatched = [item["visual_object"] for item in object_matches if item["status"] == "not_found_in_scene_graph"]
    if unmatched:
        notes.append(f"Visual objects not found in symbolic graph: {', '.join(unmatched[:8])}.")
    if not relation_matches and qwen.get("visible_relations") == []:
        notes.append("Qwen did not report explicit visible relations; this is acceptable for a single frame.")
    uncertain = qwen.get("uncertain_objects", [])
    if uncertain:
        notes.append(f"Qwen reported {len(uncertain)} uncertain visual items.")
    return notes or ["Visual-symbolic comparison completed without notable warnings."]


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _to_markdown(comparison: Dict[str, Any]) -> str:
    summary = comparison.get("summary", {})
    lines = [
        "# VirtualHome Visual-Symbolic Comparison",
        "",
        f"- success: `{comparison.get('success')}`",
        f"- reason: `{comparison.get('reason')}`",
        f"- qwen_vision_available: `{comparison.get('qwen_vision_available')}`",
        f"- frame_available: `{comparison.get('frame_available')}`",
        f"- likely_room_type: `{comparison.get('likely_room_type', '')}`",
        f"- visible_object_count: `{summary.get('visible_object_count', 0)}`",
        f"- matched_object_count: `{summary.get('matched_object_count', 0)}`",
        f"- unmatched_visual_object_count: `{summary.get('unmatched_visual_object_count', 0)}`",
        f"- symbolic_object_count: `{summary.get('symbolic_object_count', 0)}`",
        f"- relation_match_count: `{summary.get('relation_match_count', 0)}`",
        "",
        "## Confidence Notes",
        "",
    ]
    for note in comparison.get("confidence_notes", summary.get("confidence_notes", [])):
        lines.append(f"- {note}")
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
