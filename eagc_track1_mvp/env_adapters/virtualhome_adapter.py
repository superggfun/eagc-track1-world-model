from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


LOCATION_RELATIONS = {"INSIDE", "ON", "CLOSE", "FACING", "HOLDS_RH", "HOLDS_LH"}


def convert_scene_graph_to_world_model(scene_graph: Dict[str, Any], episode_id: str = "virtualhome-spike") -> Dict[str, Any]:
    nodes = scene_graph.get("nodes", [])
    edges = scene_graph.get("edges", [])
    id_to_name: Dict[Any, str] = {}
    rooms: List[Dict[str, Any]] = []
    objects: List[Dict[str, Any]] = []
    states: List[Dict[str, Any]] = []
    affordances: List[Dict[str, Any]] = []

    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        name = _node_name(node)
        if node_id is not None:
            id_to_name[node_id] = name
        category = _node_category(node)
        properties = _as_list(node.get("properties"))
        node_states = _as_list(node.get("states"))

        if category == "room":
            rooms.append({"id": str(node_id or name), "name": name, "category": "room"})
            continue

        objects.append(
            {
                "id": str(node_id or name),
                "name": name,
                "category": category,
                "location": {
                    "room": "",
                    "region": "",
                    "support": "",
                    "status": "unknown",
                    "confidence": 0.5,
                },
                "state": ",".join(str(item).lower() for item in node_states) if node_states else "",
            }
        )
        if properties:
            affordances.append(
                {
                    "object": name,
                    "actions": sorted({str(item).lower() for item in properties}),
                    "source": "virtualhome_scene_graph",
                }
            )
        for state in node_states:
            states.append({"entity": name, "attribute": "state", "value": str(state).lower()})

    relations: List[Dict[str, Any]] = []
    for index, edge in enumerate(edges if isinstance(edges, list) else []):
        if not isinstance(edge, dict):
            continue
        subject = id_to_name.get(edge.get("from_id") or edge.get("from"), str(edge.get("from_id") or edge.get("from") or ""))
        obj = id_to_name.get(edge.get("to_id") or edge.get("to"), str(edge.get("to_id") or edge.get("to") or ""))
        relation = str(edge.get("relation_type") or edge.get("relation") or "").lower()
        if not subject or not obj or not relation:
            continue
        relations.append(
            {
                "subject": subject,
                "relation": relation,
                "object": obj,
                "status": "active",
                "confidence": 0.8,
                "observed_at_step": 0,
                "source": "virtualhome_scene_graph",
            }
        )
        if relation.upper() in LOCATION_RELATIONS:
            _update_object_location(objects, subject, obj, relation)

    return {
        "episode_id": episode_id,
        "agent_state": {
            "current_room": _first_room_name(rooms),
            "holding": None,
            "step": 0,
            "last_action": "",
            "mode": "virtualhome_spike",
        },
        "rooms": rooms,
        "topology": [
            {
                "room": room["name"],
                "node_type": "room",
                "visited": room["name"] == _first_room_name(rooms),
                "frontiers": [],
            }
            for room in rooms
        ],
        "visited_rooms": [_first_room_name(rooms)] if rooms else [],
        "frontiers": [],
        "objects": objects,
        "relations": relations,
        "states": states,
        "affordances": affordances,
        "uncertainty": [],
        "plans": [],
        "exceptions": [],
        "task_status": {
            "status": "in_progress",
            "success": False,
            "reason": "VirtualHome spike conversion only; no Track 1 task evaluation.",
            "evidence": [],
        },
    }


def convert_program_log_to_episode_log(program_log: Any, episode_id: str = "virtualhome-spike") -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for step, item in enumerate(_iter_program_items(program_log)):
        if isinstance(item, dict):
            action = str(item.get("action") or item.get("script") or item.get("instruction") or item)
            result = str(item.get("result") or item.get("status") or "")
            notes = json.dumps(item, ensure_ascii=False)
        else:
            action = str(item)
            result = ""
            notes = ""
        events.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "step": step,
                "event_type": "virtualhome_program_step",
                "observation": episode_id,
                "model_update": {},
                "action": action,
                "result": result,
                "notes": notes,
            }
        )
    if not events:
        events.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "step": 0,
                "event_type": "virtualhome_spike",
                "observation": episode_id,
                "model_update": {},
                "action": "",
                "result": "no_program_log",
                "notes": "No executable program log was available.",
            }
        )
    return events


def convert_files(scene_graph_path: Path, program_log_path: Path, output_dir: Path) -> Dict[str, Path]:
    scene_graph = json.loads(scene_graph_path.read_text(encoding="utf-8"))
    program_log: Any = []
    if program_log_path.exists():
        program_log = json.loads(program_log_path.read_text(encoding="utf-8"))

    world_model = convert_scene_graph_to_world_model(scene_graph)
    episode_log = convert_program_log_to_episode_log(program_log)

    output_dir.mkdir(parents=True, exist_ok=True)
    world_model_path = output_dir / "converted_world_model.json"
    episode_log_path = output_dir / "converted_episode_log.jsonl"
    world_model_path.write_text(json.dumps(world_model, indent=2, ensure_ascii=False), encoding="utf-8")
    episode_log_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in episode_log),
        encoding="utf-8",
    )
    return {"world_model": world_model_path, "episode_log": episode_log_path}


def _node_name(node: Dict[str, Any]) -> str:
    return str(node.get("class_name") or node.get("name") or node.get("id") or "unknown").lower()


def _node_category(node: Dict[str, Any]) -> str:
    category = str(node.get("category") or "").lower()
    if category in {"rooms", "room"}:
        return "room"
    return category or str(node.get("class_name") or "object").lower()


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _first_room_name(rooms: List[Dict[str, Any]]) -> str:
    return str(rooms[0]["name"]) if rooms else "unknown"


def _iter_program_items(program_log: Any) -> Iterable[Any]:
    if isinstance(program_log, list):
        return program_log
    if isinstance(program_log, dict):
        for key in ["steps", "program", "log", "actions"]:
            value = program_log.get(key)
            if isinstance(value, list):
                return value
        return [program_log]
    return []


def _update_object_location(objects: List[Dict[str, Any]], subject: str, target: str, relation: str) -> None:
    for obj in objects:
        if obj.get("name") == subject:
            location = obj.setdefault("location", {})
            location["support"] = target
            location["status"] = "known"
            location["confidence"] = max(float(location.get("confidence") or 0.0), 0.7)
            if relation.lower() == "inside":
                location["region"] = target
            return


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert VirtualHome spike artifacts into world-model artifacts.")
    parser.add_argument("--scene-graph", default="outputs/virtualhome_spike/scene_graph.json")
    parser.add_argument("--program-log", default="outputs/virtualhome_spike/program_log.json")
    parser.add_argument("--output-dir", default="outputs/virtualhome_spike")
    args = parser.parse_args()

    paths = convert_files(Path(args.scene_graph), Path(args.program_log), Path(args.output_dir))
    print(f"Converted world model: {paths['world_model']}")
    print(f"Converted episode log: {paths['episode_log']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
