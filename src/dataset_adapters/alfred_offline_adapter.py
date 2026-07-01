from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


LOCATION_ACTION_HINTS = {"PutObject", "PickupObject", "GotoLocation", "OpenObject", "CloseObject"}


def load_traj_data(traj_path: Path) -> Dict[str, Any]:
    return json.loads(traj_path.read_text(encoding="utf-8"))


def convert_traj_file(traj_path: Path, output_dir: Path) -> Dict[str, Path]:
    traj_data = load_traj_data(traj_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    world_model = traj_to_world_model(traj_data, traj_path)
    episode_log = traj_to_episode_log(traj_data, traj_path)
    summary = traj_to_summary(traj_data, traj_path, world_model, episode_log)

    world_model_path = output_dir / "world_model.json"
    episode_log_path = output_dir / "episode_log.jsonl"
    summary_path = output_dir / "alfred_task_summary.json"

    world_model_path.write_text(json.dumps(world_model, ensure_ascii=False, indent=2), encoding="utf-8")
    episode_log_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in episode_log),
        encoding="utf-8",
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"world_model": world_model_path, "episode_log": episode_log_path, "summary": summary_path}


def traj_to_world_model(traj_data: Dict[str, Any], traj_path: Path) -> Dict[str, Any]:
    episode_id = _episode_id(traj_data, traj_path)
    instruction = extract_instruction(traj_data)
    scene_id = extract_scene_id(traj_data)
    high_level = extract_high_level_subgoals(traj_data)
    low_level = extract_low_level_actions(traj_data)
    object_names = sorted(extract_object_names(traj_data, high_level, low_level))

    objects = [
        {
            "id": name,
            "name": name,
            "category": "alfred_object",
            "location": {"room": scene_id or "", "region": "", "support": "", "status": "unknown", "confidence": 0.3},
            "state": "mentioned_in_offline_trajectory",
            "source": "alfred_offline",
        }
        for name in object_names
    ]

    action_names = sorted({item["action"] for item in high_level + low_level if item.get("action")})
    affordances = [
        {"object": name, "actions": _actions_for_object(name, high_level, low_level), "source": "alfred_offline"}
        for name in object_names
    ]
    affordances.append({"object": "agent", "actions": action_names, "source": "alfred_offline"})

    states = [{"entity": name, "attribute": "mentioned", "value": True, "source": "alfred_offline"} for name in object_names]
    rooms = [{"id": scene_id, "name": scene_id, "category": "scene"}] if scene_id else []

    return {
        "episode_id": episode_id,
        "source": "alfred_offline",
        "task": instruction,
        "agent_state": {"current_room": scene_id or "unknown", "holding": None, "step": 0, "last_action": "", "mode": "offline_dataset_conversion"},
        "rooms": rooms,
        "topology": [
            {"room": scene_id, "node_type": "scene", "visited": False, "frontiers": []}
        ]
        if scene_id
        else [],
        "visited_rooms": [],
        "frontiers": [],
        "objects": objects,
        "relations": _relations_from_actions(high_level + low_level),
        "states": states,
        "affordances": affordances,
        "uncertainty": [
            {
                "entity": "world_model",
                "attribute": "visual_state",
                "level": "high",
                "reason": "ALFRED offline trajectory files may not expose the full current visual scene, object locations, or simulator state.",
                "source": "alfred_offline",
            }
        ],
        "plans": [
            {
                "plan_id": "alfred_offline_plan",
                "source": "alfred_offline",
                "instruction": instruction,
                "subgoals": high_level,
                "actions": low_level,
            }
        ],
        "exceptions": [],
        "task_status": {
            "status": "offline_converted",
            "success": False,
            "reason": "Offline trajectory conversion only; no simulator execution or task evaluation was performed.",
            "evidence": [],
        },
        "metadata": {
            "traj_path": str(traj_path),
            "scene_id": scene_id,
            "high_level_subgoal_count": len(high_level),
            "low_level_action_count": len(low_level),
        },
    }


def traj_to_episode_log(traj_data: Dict[str, Any], traj_path: Path) -> List[Dict[str, Any]]:
    timestamp = datetime.now(timezone.utc).isoformat()
    instruction = extract_instruction(traj_data)
    high_level = extract_high_level_subgoals(traj_data)
    low_level = extract_low_level_actions(traj_data)
    events: List[Dict[str, Any]] = [
        {
            "timestamp": timestamp,
            "step": 0,
            "event_type": "task_loaded",
            "observation": str(traj_path),
            "model_update": {},
            "action": "",
            "result": "loaded",
            "notes": instruction,
        }
    ]
    step = 1
    for subgoal in high_level:
        events.append(_event(timestamp, step, "subgoal_loaded", subgoal))
        step += 1
    for action in low_level:
        events.append(_event(timestamp, step, "action_loaded", action))
        step += 1
    events.append(
        {
            "timestamp": timestamp,
            "step": step,
            "event_type": "world_model_update",
            "observation": "alfred_offline_trajectory",
            "model_update": {"source": "alfred_offline"},
            "action": "",
            "result": "world_model_approximated",
            "notes": "Converted offline task and trajectory facts into approximate world model.",
        }
    )
    events.append(
        {
            "timestamp": timestamp,
            "step": step + 1,
            "event_type": "offline_conversion_complete",
            "observation": "alfred_offline_trajectory",
            "model_update": {},
            "action": "",
            "result": "complete",
            "notes": f"subgoals={len(high_level)} actions={len(low_level)}",
        }
    )
    return events


def traj_to_summary(traj_data: Dict[str, Any], traj_path: Path, world_model: Dict[str, Any], episode_log: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "alfred_offline",
        "traj_path": str(traj_path),
        "episode_id": world_model.get("episode_id", ""),
        "task": world_model.get("task", ""),
        "scene_id": world_model.get("metadata", {}).get("scene_id", ""),
        "object_count": len(world_model.get("objects", [])),
        "subgoal_count": len(world_model.get("plans", [{}])[0].get("subgoals", [])),
        "action_count": len(world_model.get("plans", [{}])[0].get("actions", [])),
        "episode_log_event_count": len(episode_log),
        "conversion_note": "Offline ALFRED conversion only; no AI2-THOR simulator was launched.",
    }


def extract_instruction(traj_data: Dict[str, Any]) -> str:
    annotations = traj_data.get("turk_annotations", {})
    anns = annotations.get("anns") if isinstance(annotations, dict) else None
    if isinstance(anns, list) and anns:
        first = anns[0]
        if isinstance(first, dict):
            for key in ["task_desc", "high_descs", "desc"]:
                value = first.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
                if isinstance(value, list) and value:
                    return " ".join(str(item).strip() for item in value if str(item).strip())
    for key in ["task_desc", "instruction", "goal", "task"]:
        value = traj_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "ALFRED offline trajectory task"


def _episode_id(traj_data: Dict[str, Any], traj_path: Path) -> str:
    for key in ["task_id", "episode_id", "trial_id", "root"]:
        value = traj_data.get(key)
        if value not in (None, ""):
            return str(value)
    return traj_path.parent.name if traj_path.parent.name else traj_path.stem


def extract_scene_id(traj_data: Dict[str, Any]) -> str:
    scene = traj_data.get("scene", {})
    if isinstance(scene, dict):
        for key in ["floor_plan", "floorplan", "scene_num", "scene_id"]:
            value = scene.get(key)
            if value not in (None, ""):
                return str(value)
    for key in ["scene", "floor_plan", "floorplan"]:
        value = traj_data.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def extract_high_level_subgoals(traj_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    plan = traj_data.get("plan", {})
    high_pddl = plan.get("high_pddl") if isinstance(plan, dict) else []
    subgoals: List[Dict[str, Any]] = []
    for index, item in enumerate(high_pddl if isinstance(high_pddl, list) else []):
        action, args = _extract_action_and_args(item)
        subgoals.append({"index": index, "action": action or "unknown", "args": args, "raw": _compact_raw(item)})
    return subgoals


def extract_low_level_actions(traj_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    plan = traj_data.get("plan", {})
    low_actions = plan.get("low_actions") if isinstance(plan, dict) else []
    actions: List[Dict[str, Any]] = []
    for index, item in enumerate(low_actions if isinstance(low_actions, list) else []):
        action, args = _extract_action_and_args(item)
        actions.append({"index": index, "action": action or "unknown", "args": args, "raw": _compact_raw(item)})
    return actions


def extract_object_names(traj_data: Dict[str, Any], high_level: List[Dict[str, Any]], low_level: List[Dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for item in high_level + low_level:
        for arg in item.get("args", []):
            name = _normalize_object_name(str(arg))
            if name:
                names.add(name)
    pddl = traj_data.get("pddl_params", {})
    if isinstance(pddl, dict):
        for value in pddl.values():
            if isinstance(value, str):
                name = _normalize_object_name(value)
                if name:
                    names.add(name)
            elif isinstance(value, list):
                for item in value:
                    name = _normalize_object_name(str(item))
                    if name:
                        names.add(name)
    return names


def _extract_action_and_args(item: Any) -> Tuple[str, List[str]]:
    if not isinstance(item, dict):
        return str(item), []
    candidates = [
        item.get("discrete_action"),
        item.get("api_action"),
        item.get("planner_action"),
        item.get("high_pddl"),
        item,
    ]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        action = candidate.get("action") or candidate.get("action_name") or candidate.get("name")
        args = candidate.get("args") or candidate.get("arguments") or []
        if isinstance(args, str):
            args = [args]
        if action:
            extra_args = _api_object_args(candidate)
            return str(action), [str(arg) for arg in list(args) + extra_args if arg not in (None, "")]
    return "", []


def _api_object_args(candidate: Dict[str, Any]) -> List[str]:
    args: List[str] = []
    for key in ["objectId", "receptacleObjectId", "object_id", "target", "receptacle"]:
        value = candidate.get(key)
        if value:
            args.append(str(value))
    return args


def _compact_raw(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {"value": str(value)}
    compact: Dict[str, Any] = {}
    for key in ["high_idx", "low_idx", "discrete_action", "api_action", "planner_action"]:
        if key in value:
            compact[key] = value[key]
    return compact


def _event(timestamp: str, step: int, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "timestamp": timestamp,
        "step": step,
        "event_type": event_type,
        "observation": "alfred_offline_trajectory",
        "model_update": {},
        "action": payload.get("action", ""),
        "result": "loaded",
        "notes": json.dumps(payload, ensure_ascii=False),
    }


def _normalize_object_name(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    value = value.split("|", 1)[0]
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^A-Za-z0-9_/-]", "", value)
    return value.lower().strip("_")


def _actions_for_object(name: str, high_level: List[Dict[str, Any]], low_level: List[Dict[str, Any]]) -> List[str]:
    actions = set()
    for item in high_level + low_level:
        args = {_normalize_object_name(str(arg)) for arg in item.get("args", [])}
        if name in args and item.get("action"):
            actions.add(str(item["action"]))
    return sorted(actions)


def _relations_from_actions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    relations: List[Dict[str, Any]] = []
    for item in actions:
        action = str(item.get("action") or "")
        args = [_normalize_object_name(str(arg)) for arg in item.get("args", [])]
        args = [arg for arg in args if arg]
        if action in LOCATION_ACTION_HINTS and len(args) >= 2:
            relations.append(
                {
                    "subject": args[0],
                    "relation": "associated_with",
                    "object": args[1],
                    "status": "uncertain",
                    "confidence": 0.4,
                    "observed_at_step": item.get("index", 0),
                    "source": "alfred_offline_action_args",
                }
            )
    return relations
