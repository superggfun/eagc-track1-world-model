from __future__ import annotations

import random
from copy import deepcopy
from typing import Any, Dict

from env_adapters.local_sim_env import DOORS, TOPOLOGY, _initial_objects


TASK_TEMPLATES = [
    "place_object_on_target",
    "navigate_and_place",
    "place_in_container_with_fallback",
    "tool_substitution_task",
]


def generate_random_local_sim_episode(seed: int, difficulty: str = "easy") -> Dict[str, Any]:
    """Generate a deterministic hidden-style LocalSim episode spec."""
    if difficulty not in {"easy", "medium"}:
        raise ValueError("difficulty must be 'easy' or 'medium'")

    rng = random.Random(seed)
    template = TASK_TEMPLATES[(seed - 1) % len(TASK_TEMPLATES)]
    episode_id = f"random-local-sim-seed-{seed:04d}"
    objects = _serialize_objects(_initial_objects())
    doors = deepcopy(DOORS)
    recoverable = not (difficulty == "medium" and template == "place_in_container_with_fallback" and seed % 10 == 3)
    distractors: Dict[str, Dict[str, Any]] = {}
    if difficulty == "medium":
        distractors = _medium_distractors(seed)
        objects.update(distractors)
        if seed % 2 == 0:
            objects["book"]["room"] = "living_room"
            objects["book"]["region"] = "table_area"
            objects["book"]["support"] = "side_table"
        if seed % 3 == 0:
            objects["cup"]["room"] = "living_room"
            objects["cup"]["region"] = "table_area"
            objects["cup"]["support"] = "side_table"

    if template == "place_object_on_target":
        object_name, target = rng.choice([("book", "chair"), ("cup", "counter")])
        if object_name == "cup":
            start_room = "kitchen"
            task = "Find the cup and place it on the counter."
        else:
            start_room = "bedroom"
            task = "Find the book and place it on the chair."
        controlled_exception = {
            "type": "object_relocated",
            "object": object_name,
            "to_room": "kitchen" if difficulty == "medium" and object_name == "book" else ("living_room" if object_name == "book" else "kitchen"),
            "to_region": "counter_area" if difficulty == "medium" and object_name == "book" else ("table_area" if object_name == "book" else "counter_area"),
            "to_support": "counter" if difficulty == "medium" and object_name == "book" else ("side_table" if object_name == "book" else "counter"),
            "likely_locations": ["kitchen"] if difficulty == "medium" and object_name == "book" else (["living_room"] if object_name == "book" else ["kitchen"]),
            "prior_support": "bed" if object_name == "book" else "counter",
            "prior_region": "bed_area" if object_name == "book" else "counter_area",
        }
        success_condition = {
            "type": "object_on_support",
            "object": object_name,
            "target": target,
            "status": "complete",
        }
        expected_status = "complete"
    elif template == "navigate_and_place":
        start_room = "bedroom"
        task = "Go from bedroom to kitchen and place the cup on the counter."
        doors["kitchen_door"]["locked"] = True
        doors["kitchen_door"]["open"] = False
        controlled_exception = {
            "type": "door_locked",
            "object": "kitchen_door",
            "required_key": "key",
        }
        success_condition = {
            "type": "agent_room_and_object_on_support",
            "room": "kitchen",
            "object": "cup",
            "target": "counter",
            "status": "complete",
        }
        expected_status = "complete"
    elif template == "place_in_container_with_fallback":
        start_room = "kitchen"
        task = "Place the cup in the drawer."
        objects["drawer"]["available"] = False
        objects["drawer"]["state"] = "unavailable"
        fallback_target = "floor_mat" if not recoverable else "counter"
        controlled_exception = {
            "type": "target_container_unavailable",
            "object": "drawer",
            "object_to_place": "cup",
            "fallback_target": fallback_target,
            "fallback_candidates": ["counter", "side_table", "floor_mat"] if difficulty == "medium" else ["counter"],
        }
        if recoverable:
            success_condition = {
                "type": "fallback_placement",
                "object": "cup",
                "target": "drawer",
                "fallback_target": fallback_target,
                "status": "blocked_recovered",
            }
            expected_status = "blocked_recovered"
        else:
            success_condition = {
                "type": "unrecoverable",
                "object": "cup",
                "target": "drawer",
                "status": "failed",
            }
            expected_status = "failed"
    else:
        start_room = "living_room"
        task = "Tighten the loose screw with a suitable tool."
        objects["screwdriver"]["available"] = False
        controlled_exception = {
            "type": "tool_substitution",
            "object": "screwdriver",
            "substitute": "coin",
            "target": "loose_screw",
            "candidate_substitutes": ["coin", "plastic_card"] if difficulty == "medium" else ["coin"],
        }
        success_condition = {
            "type": "tool_substitution",
            "target": "loose_screw",
            "substitute_tool": "coin",
            "status": "complete",
        }
        expected_status = "complete"

    public_env_config = {
        "episode_id": episode_id,
        "template": template,
        "seed": seed,
        "difficulty": difficulty,
        "rooms": sorted(TOPOLOGY),
        "topology": deepcopy(TOPOLOGY),
        "doors": doors,
        "objects": objects,
        "object_locations": {
            name: {
                "room": obj.get("room", ""),
                "region": obj.get("region", ""),
                "support": obj.get("support", ""),
            }
            for name, obj in objects.items()
        },
        "start_room": start_room,
        "task": task,
        "recoverable": recoverable,
    }
    hidden_spec = {
        "controlled_exception": controlled_exception,
        "expected_task_status": expected_status,
        "success_condition": success_condition,
        "recoverable": recoverable,
        "hidden_object_relocation_target": _hidden_relocation_target(controlled_exception),
        "evaluator_only": True,
    }
    return {
        **public_env_config,
        **hidden_spec,
        "public_env_config": public_env_config,
        "hidden_spec": hidden_spec,
    }


def _serialize_objects(objects: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {name: dict(value) for name, value in objects.items()}


def _medium_distractors(seed: int) -> Dict[str, Dict[str, Any]]:
    return {
        f"distractor_box_{seed % 5}": {
            "category": "container",
            "room": "hallway",
            "region": "floor_area",
            "support": "",
            "visible": True,
            "pickupable": False,
            "container": True,
            "available": True,
        },
        "plastic_card": {
            "category": "tool",
            "room": "living_room",
            "region": "table_area",
            "support": "side_table",
            "visible": True,
            "pickupable": True,
            "available": False,
        },
        "floor_mat": {
            "category": "surface",
            "room": "hallway",
            "region": "floor_area",
            "support": "",
            "visible": True,
            "pickupable": False,
            "available": True,
        },
    }


def _hidden_relocation_target(controlled_exception: Dict[str, Any]) -> Dict[str, Any]:
    if controlled_exception.get("type") != "object_relocated":
        return {}
    return {
        "room": controlled_exception.get("to_room", ""),
        "region": controlled_exception.get("to_region", ""),
        "support": controlled_exception.get("to_support", ""),
    }
